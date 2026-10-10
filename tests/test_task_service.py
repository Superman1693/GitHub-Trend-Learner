"""任务服务（server/services/task_service.py）测试。

覆盖 v1.8 的三项修复：
- 日志捕获基于 contextvars，并发任务不串台
- 并发有上限、同一目标幂等去重
- 任务元数据持久化，重启可回溯（未完成任务标记为中断）

所有执行均通过假的 Orchestrator 完成，测试不触网。
"""
from __future__ import annotations

import threading
import time

import pytest

from app import log
from server.services.task_service import TaskService


@pytest.fixture
def fake_orch(monkeypatch):
    """把 orchestrator.Orchestrator 换成离线假实现。"""
    import app.orchestrator as orch_mod

    class FakeOrch:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def run_repo(self, url: str) -> dict:
            return {"ok": True, "path": f"outputs/{url.replace('/', '_')}.md"}

        def run_daily(self, top_n=None, no_mail=True) -> dict:
            return {"ok": True, "date": "2026-10-09"}

    monkeypatch.setattr(orch_mod, "Orchestrator", FakeOrch)
    yield FakeOrch


def _wait(svc: TaskService, tasks, timeout: float = 8.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if all(svc.get(t.task_id).status not in ("pending", "running") for t in tasks):
            return
        time.sleep(0.02)
    raise AssertionError("任务未在超时时间内结束")


def test_dedup_same_target(tmp_path, fake_orch):
    """同一目标在途时重复提交应返回同一个任务，不重复消耗配额。"""
    svc = TaskService(store=tmp_path / "tasks.json", max_workers=2)
    release = threading.Event()

    def slow(_orch):
        release.wait(5)
        return {"ok": True}

    first = svc._submit("repo", "a/b", slow)
    second = svc._submit("repo", "a/b", slow)
    assert first.task_id == second.task_id

    release.set()
    _wait(svc, [first])
    # 完成后再提交应产生新任务
    third = svc._submit("repo", "a/b", slow)
    assert third.task_id != first.task_id
    release.set()
    _wait(svc, [third])


def test_concurrency_is_capped(tmp_path, fake_orch):
    svc = TaskService(store=tmp_path / "tasks.json", max_workers=2)
    lock = threading.Lock()
    state = {"cur": 0, "peak": 0}

    def runner(_orch):
        with lock:
            state["cur"] += 1
            state["peak"] = max(state["peak"], state["cur"])
        time.sleep(0.12)
        with lock:
            state["cur"] -= 1
        return {"ok": True}

    tasks = [svc._submit("repo", f"x/r{i}", runner) for i in range(5)]
    _wait(svc, tasks)
    assert state["peak"] <= 2, f"并发峰值 {state['peak']} 超过上限 2"


def test_log_capture_is_isolated(tmp_path, fake_orch):
    """两个任务并发写日志时，各自只应收到自己的输出（回归 redirect_stdout 串台缺陷）。"""
    svc = TaskService(store=tmp_path / "tasks.json", max_workers=2)
    barrier = threading.Barrier(2, timeout=5)

    def make(tag: str):
        def runner(_orch):
            barrier.wait()
            for i in range(6):
                log.console(f"{tag}-line-{i}")
            return {"ok": True}
        return runner

    a = svc._submit("repo", "x/a", make("AAA"))
    b = svc._submit("repo", "x/b", make("BBB"))
    _wait(svc, [a, b])

    a_log = "\n".join(svc.get(a.task_id).log)
    b_log = "\n".join(svc.get(b.task_id).log)
    assert "AAA-line-0" in a_log and "BBB-line-0" not in a_log
    assert "BBB-line-0" in b_log and "AAA-line-0" not in b_log


def test_persistence_and_restart(tmp_path, fake_orch):
    store = tmp_path / "tasks.json"
    svc = TaskService(store=store, max_workers=2)
    task = svc._submit("repo", "a/b", lambda _o: {"ok": True})
    _wait(svc, [task])
    assert store.is_file()

    revived = TaskService(store=store, max_workers=2)
    restored = revived.get(task.task_id)
    assert restored is not None
    assert restored.status == "succeeded"


def test_restart_marks_unfinished_as_failed(tmp_path):
    store = tmp_path / "tasks.json"
    store.write_text(
        '{"tasks":[{"task_id":"zzz","kind":"repo","target":"a/b","status":"running",'
        '"created_at":"2026-10-09 10:00:00","log":[]}]}',
        encoding="utf-8",
    )
    svc = TaskService(store=store, max_workers=1)
    task = svc.get("zzz")
    assert task is not None
    assert task.status == "failed"
    assert "重启" in (task.error or "")


def test_retry_reuses_target(tmp_path, fake_orch):
    svc = TaskService(store=tmp_path / "tasks.json", max_workers=2)
    failed = svc._submit("repo", "a/b", lambda _o: {"ok": False, "error": "boom"})
    _wait(svc, [failed])
    assert svc.get(failed.task_id).status == "failed"

    again = svc.retry(failed.task_id)
    assert again is not None
    assert again.retried_from == failed.task_id
    assert again.target == "a/b"
    _wait(svc, [again])


def test_retry_rejects_running(tmp_path, fake_orch):
    svc = TaskService(store=tmp_path / "tasks.json", max_workers=1)
    release = threading.Event()
    running = svc._submit("repo", "a/b", lambda _o: (release.wait(5), {"ok": True})[1])
    assert svc.retry(running.task_id) is None
    release.set()
    _wait(svc, [running])
