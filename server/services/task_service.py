"""任务服务：在后台线程池执行解析/每日任务，并提供状态与实时日志查询。

v1.8 关键修复与增强：
1. **日志捕获不再替换全局 stdout**。原实现用 `redirect_stdout` 替换进程级 `sys.stdout`，
   并发任务会互相串日志、退出时还原错乱。现改为 `app.log.capture()`（基于 contextvars），
   每个任务只收到自己线程内产生的日志。
2. **并发上限 + 幂等去重**。原实现每次提交都新起线程，无上限、可重复提交同一仓库；
   现改用固定大小线程池，并对 (kind, target) 做在途去重。
3. **任务持久化**。任务元数据落 `cache/tasks.json`，服务重启后可回溯（原为纯内存）。
"""
from __future__ import annotations

import json
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from app import log
from app.config import CACHE_DIR
from app.fsutil import atomic_write_json

MAX_LOG_LINES = 400
MAX_TASKS = 50
MAX_CONCURRENT_TASKS = 3          # 与 app.config.concurrency 同量级，避免同时打满 GitHub 限流
TASK_STORE: Path = CACHE_DIR / "tasks.json"


@dataclass
class Task:
    task_id: str
    kind: str  # repo | daily
    target: str
    status: str = "pending"  # pending | running | succeeded | failed
    created_at: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    report: dict | None = None
    error: str | None = None
    retried_from: str | None = None
    log: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class TaskService:
    """任务注册表 + 执行器（元数据持久化到 cache/tasks.json）。"""

    def __init__(self, store: Path | None = None,
                 max_workers: int = MAX_CONCURRENT_TASKS) -> None:
        self._tasks: dict[str, Task] = {}
        self._order: list[str] = []
        self._lock = threading.Lock()
        self._inflight: dict[tuple[str, str], str] = {}
        self._pool = ThreadPoolExecutor(max_workers=max_workers,
                                        thread_name_prefix="gtl-task")
        self._store: Path | None = store if store is not None else TASK_STORE
        self._load()

    # ---- 持久化 ----

    def _load(self) -> None:
        if self._store is None or not self._store.is_file():
            return
        try:
            payload = json.loads(self._store.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - 存储损坏不应阻止服务启动
            return
        for raw in payload.get("tasks") or []:
            if not isinstance(raw, dict):
                continue
            fields = {k: v for k, v in raw.items() if k in Task.__dataclass_fields__}
            try:
                task = Task(**fields)
            except TypeError:
                continue
            if task.status in ("pending", "running"):
                # 进程重启时未完成的任务不可能恢复，标记为中断而非永远挂起
                task.status = "failed"
                task.error = task.error or "服务重启导致任务中断"
                task.finished_at = task.finished_at or _now()
            self._tasks[task.task_id] = task
            self._order.append(task.task_id)
        self._order = self._order[-MAX_TASKS:]

    def _persist(self) -> None:
        if self._store is None:
            return
        snapshot = {"tasks": [self._tasks[t].to_dict() for t in self._order if t in self._tasks]}
        try:
            atomic_write_json(self._store, snapshot, indent=1)
        except OSError:
            pass  # 持久化失败不影响任务执行

    # ---- 查询 ----

    def get(self, task_id: str) -> Task | None:
        with self._lock:
            return self._tasks.get(task_id)

    def list_recent(self, limit: int = 20) -> list[Task]:
        with self._lock:
            return [self._tasks[t] for t in reversed(self._order[-limit:]) if t in self._tasks]

    # ---- 提交 ----

    def submit_repo(self, url: str) -> Task:
        return self._submit("repo", url, lambda orch: orch.run_repo(url))

    def submit_daily(self, top_n: int | None = None, no_mail: bool = True) -> Task:
        label = f"top={top_n or 'default'}"
        return self._submit(
            "daily", label, lambda orch: orch.run_daily(top_n=top_n, no_mail=no_mail)
        )

    def retry(self, task_id: str) -> Task | None:
        """以失败任务的目标重新提交一个任务（保留 retried_from 便于追溯）。"""
        old = self.get(task_id)
        if old is None or old.status in ("pending", "running"):
            return None
        if old.kind == "repo":
            task = self.submit_repo(old.target)
        else:
            top_raw = old.target.partition("=")[2]
            try:
                top_n = None if top_raw in ("", "default") else int(top_raw)
            except ValueError:
                top_n = None
            task = self.submit_daily(top_n=top_n, no_mail=True)
        task.retried_from = task_id
        with self._lock:
            self._persist()
        return task

    def _submit(self, kind: str, target: str, runner) -> Task:
        key = (kind, target)
        with self._lock:
            # 幂等：同一目标已有在途任务时直接返回，避免重复消耗 LLM 与 GitHub 配额
            existing_id = self._inflight.get(key)
            existing = self._tasks.get(existing_id) if existing_id else None
            if existing is not None and existing.status in ("pending", "running"):
                return existing

            task = Task(task_id=uuid.uuid4().hex[:12], kind=kind, target=target,
                        created_at=_now())
            self._tasks[task.task_id] = task
            self._order.append(task.task_id)
            self._inflight[key] = task.task_id
            for stale in self._order[:-MAX_TASKS]:
                self._tasks.pop(stale, None)
            self._order = self._order[-MAX_TASKS:]
            self._persist()

        self._pool.submit(self._execute, task, runner, key)
        return task

    # ---- 执行 ----

    def _execute(self, task: Task, runner, key: tuple[str, str]) -> None:
        task.status = "running"
        task.started_at = _now()
        task.log.append(f"[{task.started_at}] 任务开始：{task.kind} {task.target}")
        self._persist()
        try:
            from app.orchestrator import Orchestrator

            # 日志走 contextvars 捕获（而非替换全局 stdout），并发任务互不串台
            with log.capture(task.log):
                report = runner(Orchestrator())
            task.report = report if isinstance(report, dict) else {"raw": str(report)}
            task.status = "succeeded" if task.report.get("ok", True) else "failed"
            if task.status == "failed" and not task.error:
                task.error = str(task.report.get("error") or "任务返回失败状态")
        except Exception as exc:  # noqa: BLE001 - 任务边界需兜住全部异常
            task.status = "failed"
            task.error = f"{type(exc).__name__}: {exc}"
            task.log.append(traceback.format_exc(limit=3))
        finally:
            task.finished_at = _now()
            task.log.append(f"[{task.finished_at}] 任务结束：{task.status}")
            with self._lock:
                self._inflight.pop(key, None)
                self._persist()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


service = TaskService()
