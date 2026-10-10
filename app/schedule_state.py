"""调度状态（v1.8.3）。

**问题**：`main.py serve` 是独立进程，Web 控制台是另一个进程，两者不共享内存——
前端完全不知道定时任务到底在不在跑、下次什么时候执行。

**方案**：serve 进程把状态写进 `cache/schedule-state.json`，控制台读它。
为了让「是否在跑」可判断，serve 在等待期间**分片睡眠**（每 30s 写一次心跳），
而不是一次 `sleep` 几个小时——否则整个等待期都没有心跳，无从判断存活。
分片睡眠的附带好处：Ctrl+C 响应更及时。

判定规则：心跳距今超过 `STALE_AFTER` 秒即视为未运行（进程被杀/机器重启都会命中）。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from .config import CACHE_DIR
from .fsutil import atomic_write_json

FILENAME = "schedule-state.json"
HEARTBEAT_INTERVAL = 30      # serve 进程写心跳的间隔（秒）
STALE_AFTER = 90             # 超过这么久没心跳就认为没在跑


def _path() -> Path:
    return CACHE_DIR / FILENAME


def write(**fields) -> None:
    """写入/更新状态（合并式：未传的字段保留原值）。"""
    data = read() or {}
    data.update(fields)
    data["heartbeat"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        atomic_write_json(_path(), data, indent=1)
    except OSError:
        pass          # 状态写不进去不应影响定时任务本身


def read() -> dict | None:
    path = _path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def clear() -> None:
    """进程正常退出时清掉状态，避免前端显示「正在运行」。"""
    try:
        _path().unlink()
    except OSError:
        pass


def _age_seconds(heartbeat: str | None) -> float | None:
    if not heartbeat:
        return None
    try:
        beat = datetime.strptime(heartbeat, "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None
    return (datetime.now() - beat).total_seconds()


def snapshot() -> dict:
    """给 API 用的只读视图。

    从未启动过、心跳过期、状态文件损坏都统一表现为 `running: false`，
    并给出 `reason` 说明原因，前端无需自己推断。
    """
    data = read()
    if not data:
        return {
            "running": False,
            "reason": "never_started",
            "message": "定时任务从未启动过。执行 `python main.py serve --at 09:00` 可开启。",
            "at": None,
            "next_run_at": None,
            "last_run_at": None,
            "last_result": None,
            "heartbeat": None,
            "stale_seconds": None,
        }

    age = _age_seconds(data.get("heartbeat"))
    running = age is not None and age <= STALE_AFTER

    if running:
        reason, message = "running", "定时任务正在运行"
    elif age is None:
        reason, message = "unknown_heartbeat", "状态文件缺少有效心跳，无法判断运行状态"
    else:
        reason = "stale"
        message = f"定时任务已停止（最后一次心跳 {int(age)} 秒前）"

    return {
        "running": running,
        "reason": reason,
        "message": message,
        "at": data.get("at"),
        "next_run_at": data.get("next_run_at"),
        "last_run_at": data.get("last_run_at"),
        "last_result": data.get("last_result"),
        "heartbeat": data.get("heartbeat"),
        "stale_seconds": int(age) if age is not None else None,
        "started_at": data.get("started_at"),
        "pid": data.get("pid"),
    }


def next_run_at(at: str, now: datetime | None = None) -> str:
    """按 `HH:MM` 计算下一次执行时刻（当天已过则顺延到明天）。"""
    now = now or datetime.now()
    try:
        target = datetime.strptime(f"{now:%Y-%m-%d} {at}", "%Y-%m-%d %H:%M")
    except ValueError:
        return ""
    if target <= now:
        target += timedelta(days=1)
    return target.strftime("%Y-%m-%d %H:%M")
