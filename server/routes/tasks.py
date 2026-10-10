"""任务路由：提交解析任务并查询进度与日志。"""
from __future__ import annotations

import re

from app.config import MAX_AUTO_PARSE

from ..http import Request, Response, Router, error, json_response
from ..services import task_service

_REPO_PATTERN = re.compile(r"^(https?://(www\.)?github\.com/[\w.-]+/[\w.-]+/?|[\w.-]+/[\w.-]+)$")


def submit_task(req: Request) -> Response:
    try:
        payload = req.json()
    except ValueError as exc:
        return error(400, str(exc), code="INVALID_BODY")

    kind = str(payload.get("kind") or "").strip()
    if kind == "repo":
        url = str(payload.get("url") or "").strip()
        if not _REPO_PATTERN.match(url):
            return error(
                400,
                "仓库地址格式不正确，应为 https://github.com/owner/repo 或 owner/repo",
                code="INVALID_REPO_URL",
            )
        task = task_service.service.submit_repo(url)
    elif kind == "daily":
        top_raw = payload.get("top")
        try:
            top_n = int(top_raw) if top_raw not in (None, "") else None
        except (TypeError, ValueError):
            return error(400, "top 必须是整数", code="INVALID_TOP")
        # 上界校验：每个仓库都会调用多次 LLM，放开上界等于放开成本（v1.8）
        if top_n is not None and not (1 <= top_n <= MAX_AUTO_PARSE):
            return error(
                400,
                f"top 必须在 1–{MAX_AUTO_PARSE} 之间（当前 {top_n}）",
                code="INVALID_TOP_RANGE",
            )
        task = task_service.service.submit_daily(top_n=top_n, no_mail=True)
    else:
        return error(400, "kind 必须是 repo 或 daily", code="INVALID_KIND")

    return json_response(task.to_dict(), status=202)


def list_tasks(req: Request) -> Response:
    try:
        limit = int(req.q("limit") or 20)
    except ValueError:
        limit = 20
    limit = max(1, min(limit, 50))
    items = [t.to_dict() for t in task_service.service.list_recent(limit)]
    return json_response({"total": len(items), "items": items})


def get_task(req: Request) -> Response:
    task = task_service.service.get(req.path_params.get("task_id", ""))
    if task is None:
        return error(404, "任务不存在或已过期", code="TASK_NOT_FOUND")
    return json_response(task.to_dict())


def retry_task(req: Request) -> Response:
    """以失败任务的目标重新提交（v1.8）：失败后无需手动重填地址。"""
    task = task_service.service.retry(req.path_params.get("task_id", ""))
    if task is None:
        return error(409, "该任务不存在、仍在进行中，或不支持重试", code="TASK_NOT_RETRYABLE")
    return json_response(task.to_dict(), status=202)


def register(router: Router) -> None:
    router.post("/api/tasks", submit_task)
    router.get("/api/tasks", list_tasks)
    router.get("/api/tasks/{task_id}", get_task)
    router.post("/api/tasks/{task_id}/retry", retry_task)
