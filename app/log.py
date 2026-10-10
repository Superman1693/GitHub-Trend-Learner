"""运行日志（NFR4）：JSONL 文件 + 控制台摘要。

字段至少含：task_id、trace_id、agent、status、attempt、duration_ms、error（global.md §6.3、NFR4）。
Token 消耗仅作记录，不作约束（Q4）。
"""
from __future__ import annotations

import contextlib
import contextvars
import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

from .config import LOGS_DIR

_LOCK = threading.Lock()

# 当前线程的日志收集器（v1.8）。
# 用 contextvars 而非替换全局 sys.stdout：并发任务各写各的缓冲，互不串台。
# contextvars 在新建线程时复制当前上下文，因此每个任务线程设置的值只对该线程可见。
_SINK: contextvars.ContextVar[list[str] | None] = contextvars.ContextVar(
    "gtl_log_sink", default=None
)
MAX_CAPTURE_LINES = 400


@contextlib.contextmanager
def capture(sink: list[str]):
    """把本线程内 `console()` 的输出同时收集到 `sink`。"""
    token = _SINK.set(sink)
    try:
        yield sink
    finally:
        _SINK.reset(token)


def console(msg: str) -> None:
    text = str(msg)
    try:
        sys.stdout.write(text + "\n")
        sys.stdout.flush()
    except Exception:
        pass
    sink = _SINK.get()
    if sink is not None:
        for line in text.splitlines():
            if line.strip():
                sink.append(line.rstrip())
        del sink[:-MAX_CAPTURE_LINES]


def _log_file() -> Path:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return LOGS_DIR / f"run-{datetime.now():%Y%m%d}.jsonl"


def event(task_id: str, trace_id: str, agent: str, status: str, attempt: int = 0,
          duration_ms: int = 0, error: str = "", tokens: int = 0, **extra) -> None:
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "task_id": task_id,
        "trace_id": trace_id,
        "agent": agent,
        "status": status,
        "attempt": attempt,
        "duration_ms": round(duration_ms),
        "error": str(error)[:500],
        "tokens": tokens,
    }
    record.update(extra)
    line = json.dumps(record, ensure_ascii=False)
    try:
        with _LOCK:
            with _log_file().open("a", encoding="utf-8") as f:
                f.write(line + "\n")
    except OSError as exc:
        # 日志系统不应成为故障源：磁盘满 / 权限变更时降级为控制台提示，不中断主流程（v1.8）
        console(f"[log] 事件日志写入失败（已忽略）：{exc}")
