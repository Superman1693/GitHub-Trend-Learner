"""调度状态（app/schedule_state.py）测试。

核心是**判定「定时任务在不在跑」**：serve 是独立进程，只能靠心跳文件推断。
判错的后果很直接——前端显示「正在运行」但实际早挂了，用户以为任务照常跑，
结果几天没有新文档。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from app import schedule_state as ss


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(ss, "CACHE_DIR", tmp_path)
    return tmp_path


def _write_raw(store, data: dict):
    (store / ss.FILENAME).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _beat(seconds_ago: int) -> str:
    return (datetime.now() - timedelta(seconds=seconds_ago)).strftime("%Y-%m-%d %H:%M:%S")


# ---------------- 基础读写 ----------------

def test_never_started(store):
    snap = ss.snapshot()
    assert snap["running"] is False
    assert snap["reason"] == "never_started"
    assert "main.py serve" in snap["message"]


def test_write_then_read_roundtrip(store):
    ss.write(at="09:00", next_run_at="2026-10-11 09:00")
    data = ss.read()
    assert data["at"] == "09:00"
    assert data["next_run_at"] == "2026-10-11 09:00"
    assert data["heartbeat"]


def test_write_is_merge_not_replace(store):
    """心跳更新不能把 at / next_run_at 冲掉。"""
    ss.write(at="09:00", next_run_at="2026-10-11 09:00")
    ss.write(last_run_at="2026-10-10 09:00")

    data = ss.read()
    assert data["at"] == "09:00"
    assert data["next_run_at"] == "2026-10-11 09:00"
    assert data["last_run_at"] == "2026-10-10 09:00"


def test_clear_removes_file(store):
    ss.write(at="09:00")
    ss.clear()
    assert ss.read() is None
    assert ss.snapshot()["reason"] == "never_started"


def test_clear_on_missing_file_is_safe(store):
    ss.clear()          # 不应抛异常


def test_corrupted_file_treated_as_never_started(store):
    (store / ss.FILENAME).write_text("{坏掉的 JSON", encoding="utf-8")
    assert ss.read() is None
    assert ss.snapshot()["reason"] == "never_started"


def test_non_dict_json_treated_as_never_started(store):
    (store / ss.FILENAME).write_text("[1,2]", encoding="utf-8")
    assert ss.read() is None


# ---------------- 运行状态判定 ----------------

def test_fresh_heartbeat_means_running(store):
    _write_raw(store, {"at": "09:00", "heartbeat": _beat(5)})
    snap = ss.snapshot()
    assert snap["running"] is True
    assert snap["reason"] == "running"


def test_heartbeat_just_inside_window_is_running(store):
    """阈值内应算在跑。

    注意不要在**恰好等于**阈值处断言：心跳是秒级字符串，
    `_beat(90)` 解析回来实际是 90.x 秒，会落到边界外侧。
    """
    _write_raw(store, {"at": "09:00", "heartbeat": _beat(ss.STALE_AFTER - 5)})
    assert ss.snapshot()["running"] is True


def test_heartbeat_just_outside_window_is_stopped(store):
    _write_raw(store, {"at": "09:00", "heartbeat": _beat(ss.STALE_AFTER + 5)})
    assert ss.snapshot()["running"] is False


def test_stale_heartbeat_means_stopped(store):
    _write_raw(store, {"at": "09:00", "heartbeat": _beat(ss.STALE_AFTER + 60)})
    snap = ss.snapshot()
    assert snap["running"] is False
    assert snap["reason"] == "stale"
    assert "已停止" in snap["message"]
    assert snap["stale_seconds"] >= ss.STALE_AFTER


def test_missing_heartbeat_is_unknown(store):
    _write_raw(store, {"at": "09:00"})
    snap = ss.snapshot()
    assert snap["running"] is False
    assert snap["reason"] == "unknown_heartbeat"


def test_malformed_heartbeat_is_unknown(store):
    _write_raw(store, {"at": "09:00", "heartbeat": "昨天"})
    assert ss.snapshot()["reason"] == "unknown_heartbeat"


def test_snapshot_passes_through_run_history(store):
    _write_raw(store, {
        "at": "09:00", "heartbeat": _beat(3),
        "last_run_at": "2026-10-10 09:00", "last_result": "degraded",
        "next_run_at": "2026-10-11 09:00", "started_at": "2026-10-08 08:00", "pid": 1234,
    })
    snap = ss.snapshot()
    assert snap["last_result"] == "degraded"
    assert snap["last_run_at"] == "2026-10-10 09:00"
    assert snap["next_run_at"] == "2026-10-11 09:00"
    assert snap["pid"] == 1234


# ---------------- 下次执行时刻 ----------------

def test_next_run_today_when_time_not_passed():
    now = datetime(2026, 10, 10, 8, 0)
    assert ss.next_run_at("09:00", now) == "2026-10-10 09:00"


def test_next_run_tomorrow_when_time_passed():
    now = datetime(2026, 10, 10, 10, 0)
    assert ss.next_run_at("09:00", now) == "2026-10-11 09:00"


def test_next_run_at_exact_now_rolls_to_tomorrow():
    """刚好等于执行时刻时应排到明天，否则会立刻重复触发。"""
    now = datetime(2026, 10, 10, 9, 0)
    assert ss.next_run_at("09:00", now) == "2026-10-11 09:00"


def test_next_run_invalid_time_returns_empty():
    assert ss.next_run_at("25:99") == ""
    assert ss.next_run_at("abc") == ""


def test_next_run_crosses_month_boundary():
    now = datetime(2026, 10, 31, 23, 0)
    assert ss.next_run_at("09:00", now) == "2026-11-01 09:00"


# ---------------- 路由 ----------------

def test_route_returns_snapshot(store):
    from server.http.request import Request
    from server.routes.system import schedule

    ss.write(at="09:00", next_run_at="2026-10-11 09:00")
    resp = schedule(Request.from_raw("GET", "/api/system/schedule", {}, b""))

    assert resp.status == 200
    payload = json.loads(resp.body)
    assert payload["running"] is True
    assert payload["at"] == "09:00"


def test_route_registered():
    from server.app import build_router

    assert ("GET", "/api/system/schedule") in set(build_router().routes())
