"""运行指标聚合（app/metrics.py）测试。

指标是给人做判断用的，**算错比不算更糟**。这里重点锁两类语义：
1. `success_rate = None` 表示「日志里没有终态记录、无从计算」，
   不能被当成 0%（否则 OrchestratorAgent 会显示「成功率 0%」而它其实只失败 4/19）；
2. 日志被中断截断出的半行必须跳过，不能让整块指标失败。
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from app import metrics


@pytest.fixture
def logs(tmp_path, monkeypatch):
    monkeypatch.setattr(metrics, "LOGS_DIR", tmp_path)
    return tmp_path


def _write(store, day_offset: int, records: list[dict]):
    day = date.today() - timedelta(days=day_offset)
    path = store / f"run-{day:%Y%m%d}.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return path


def _ev(agent, status, **kw) -> dict:
    base = {"ts": "2026-10-10T00:00:00+00:00", "task_id": "t1", "trace_id": "t1",
            "agent": agent, "status": status, "attempt": 0, "duration_ms": 0,
            "error": "", "tokens": 0}
    base.update(kw)
    return base


# ---------------- 空与容错 ----------------

def test_no_logs_returns_zeroed_shape(logs):
    m = metrics.collect()
    assert m["range"]["events"] == 0
    assert m["tasks"]["started"] == 0
    assert m["tasks"]["success_rate"] is None
    assert m["cache"]["hit_rate"] is None
    assert m["agents"] == {}
    assert m["slowest"] == [] and m["recent_errors"] == []


def test_skips_truncated_lines(logs):
    """回归：日志是追加写的，进程被杀会留下半行 JSON。"""
    path = _write(logs, 0, [_ev("TutorAgent", "done", duration_ms=100)])
    with path.open("a", encoding="utf-8") as fh:
        fh.write('{"ts": "2026-10-10T00:00:00+00:00", "agent": "TutorAg')   # 半行

    m = metrics.collect()
    assert m["range"]["events"] == 1, "坏行应被跳过而不是让整个聚合失败"
    assert m["agents"]["TutorAgent"]["calls"] == 1


def test_skips_blank_lines_and_non_objects(logs):
    path = _write(logs, 0, [_ev("TutorAgent", "done")])
    with path.open("a", encoding="utf-8") as fh:
        fh.write("\n\n[1,2,3]\n")

    assert metrics.collect()["range"]["events"] == 1


def test_ignores_files_with_unexpected_names(logs):
    (logs / "run-notadate.jsonl").write_text(
        json.dumps(_ev("X", "done")) + "\n", encoding="utf-8")
    assert metrics.collect()["range"]["events"] == 0


# ---------------- 窗口筛选 ----------------

def test_window_excludes_old_files(logs):
    _write(logs, 0, [_ev("A", "done")])
    _write(logs, 30, [_ev("A", "done")])

    assert metrics.collect(days=7)["range"]["files"] == 1
    assert metrics.collect(days=60)["range"]["files"] == 2


def test_days_is_clamped(logs):
    _write(logs, 0, [_ev("A", "done")])
    assert metrics.collect(days=0)["range"]["days"] == 1
    assert metrics.collect(days=9999)["range"]["days"] == 90


# ---------------- 任务指标 ----------------

def test_task_success_rate_uses_started_minus_failed(logs):
    _write(logs, 0, [
        _ev("OrchestratorAgent", "start"),
        _ev("OrchestratorAgent", "start"),
        _ev("OrchestratorAgent", "start"),
        _ev("OrchestratorAgent", "start"),
        _ev("OrchestratorAgent", "failed"),
    ])
    m = metrics.collect()
    assert m["tasks"] == {"started": 4, "failed": 1, "retry": 0, "success_rate": 0.75}


def test_task_retry_counted_separately(logs):
    _write(logs, 0, [_ev("OrchestratorAgent", "start"), _ev("OrchestratorAgent", "retry")])
    m = metrics.collect()
    assert m["tasks"]["retry"] == 1
    assert m["tasks"]["success_rate"] == 1.0


# ---------------- Agent 成功率语义（关键）----------------

def test_agent_rate_none_when_no_done_recorded(logs):
    """OrchestratorAgent 不记录 done —— 必须返回 None，不能算成 0%。"""
    _write(logs, 0, [_ev("OrchestratorAgent", "start")] * 10
                    + [_ev("OrchestratorAgent", "failed")] * 4)
    stat = metrics.collect()["agents"]["OrchestratorAgent"]
    assert stat["success_rate"] is None
    assert stat["failed"] == 4, "原始计数照常给出"


def test_agent_rate_computed_when_done_present(logs):
    _write(logs, 0, [_ev("TutorAgent", "done")] * 3 + [_ev("TutorAgent", "failed")])
    assert metrics.collect()["agents"]["TutorAgent"]["success_rate"] == 0.75


def test_cache_agent_has_no_success_rate(logs):
    _write(logs, 0, [_ev("cache", "hit"), _ev("cache", "stored")])
    assert metrics.collect()["agents"]["cache"]["success_rate"] is None


# ---------------- 耗时 ----------------

def test_avg_and_p95_duration(logs):
    _write(logs, 0, [_ev("A", "done", duration_ms=d) for d in (100, 200, 300, 400, 5000)])
    stat = metrics.collect()["agents"]["A"]
    assert stat["avg_ms"] == 1200
    assert stat["p95_ms"] == 5000
    assert stat["duration_samples"] == 5


def test_negative_duration_ignored(logs):
    """异常负值不应污染统计。"""
    _write(logs, 0, [_ev("A", "done", duration_ms=100), _ev("A", "done", duration_ms=-5)])
    stat = metrics.collect()["agents"]["A"]
    assert stat["avg_ms"] == 100
    assert stat["duration_samples"] == 1


def test_slowest_sorted_desc_and_capped(logs):
    _write(logs, 0, [_ev("A", "done", duration_ms=d) for d in range(10)])
    slowest = metrics.collect()["slowest"]
    assert len(slowest) == 5
    assert [s["duration_ms"] for s in slowest] == [9, 8, 7, 6, 5]


# ---------------- 缓存命中率（闭环 T16）----------------

def test_cache_hit_rate(logs):
    _write(logs, 0, [_ev("cache", "hit")] * 3 + [_ev("cache", "stored")])
    c = metrics.collect()["cache"]
    assert c == {"hit": 3, "stored": 1, "lookups": 4, "hit_rate": 0.75}


def test_cache_hit_rate_none_without_lookups(logs):
    _write(logs, 0, [_ev("TutorAgent", "done")])
    assert metrics.collect()["cache"]["hit_rate"] is None


# ---------------- token 与门禁 ----------------

def test_token_totals(logs):
    _write(logs, 0, [
        _ev("OrchestratorAgent", "start"),
        _ev("OrchestratorAgent", "start"),
        _ev("TutorAgent", "done", tokens=1000),
        _ev("TutorAgent", "done", tokens=500),
    ])
    tok = metrics.collect()["tokens"]
    assert tok["total"] == 1500
    assert tok["avg_per_task"] == 750


def test_gate_distribution(logs):
    _write(logs, 0, [_ev("TutorAgent", "done", gate_result="pass")] * 2
                    + [_ev("TutorAgent", "done", gate_result="degraded")])
    assert metrics.collect()["gate"] == {"pass": 2, "degraded": 1}


# ---------------- 错误 ----------------

def test_recent_errors_newest_first_and_capped(logs):
    records = [_ev("A", "failed", error=f"err{i}", ts=f"2026-10-0{i + 1}T00:00:00+00:00")
               for i in range(7)]
    _write(logs, 0, records)
    errs = metrics.collect()["recent_errors"]
    assert len(errs) == 5
    assert errs[0]["error"] == "err6", "最新的错误排最前"


def test_empty_error_string_not_collected(logs):
    _write(logs, 0, [_ev("A", "done", error="")])
    assert metrics.collect()["recent_errors"] == []


# ---------------- 路由 ----------------

def test_route_returns_metrics(logs):
    from server.http.request import Request
    from server.routes.system import metrics as route

    _write(logs, 0, [_ev("OrchestratorAgent", "start")])
    resp = route(Request.from_raw("GET", "/api/system/metrics?days=7", {}, b""))

    assert resp.status == 200
    payload = json.loads(resp.body)
    assert payload["tasks"]["started"] == 1


def test_route_tolerates_bad_days(logs):
    from server.http.request import Request
    from server.routes.system import metrics as route

    resp = route(Request.from_raw("GET", "/api/system/metrics?days=abc", {}, b""))
    assert json.loads(resp.body)["range"]["days"] == 7


def test_route_registered():
    from server.app import build_router

    assert ("GET", "/api/system/metrics") in set(build_router().routes())
