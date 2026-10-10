"""系统路由：健康检查、运行配置、产出概览。"""
from __future__ import annotations

from datetime import datetime

from app import __version__ as app_version
from app import metrics as metrics_service
from app import schedule_state

from ..http import Request, Response, Router, json_response
from ..http.static import dist_summary
from ..services import document_service, task_service


def _config_snapshot() -> dict:
    """返回运行配置（敏感值只报告是否配置，不回显内容，NFR6）。"""
    from app.config import Settings
    from app.contracts import module_specs

    s = Settings.load()
    return {
        "github_token": {"configured": bool(s.github_token)},
        "llm": {"ready": bool(s.llm_ready), "model": s.llm_model if s.llm_ready else None},
        "smtp": {"ready": bool(s.smtp_ready)},
        "concurrency": s.concurrency,
        "max_retries": s.max_retries,
        "max_gate_returns": s.max_gate_returns,
        # 六模块规范由后端单一来源透出，前端不再硬编码副本（v1.8）
        "modules": module_specs(),
        "version": app_version,
    }


def health(_req: Request) -> Response:
    return json_response(
        {
            "status": "ok",
            "service": "github-trend-learner-ui",
            "version": app_version,
            "time": datetime.now().isoformat(timespec="seconds"),
            "frontend": dist_summary(),
        }
    )


def config(_req: Request) -> Response:
    try:
        return json_response(_config_snapshot())
    except Exception as exc:  # noqa: BLE001 - 配置异常不应导致接口 500 崩掉
        return json_response({"error": {"code": "CONFIG_ERROR", "message": str(exc)}}, status=200)


def overview(_req: Request) -> Response:
    return json_response(
        {
            "documents": document_service.stats(),
            "tasks": {
                "running": sum(
                    1 for t in task_service.service.list_recent(50) if t.status == "running"
                ),
                "total": len(task_service.service.list_recent(50)),
            },
        }
    )


_openapi_cache: dict | None = None


def schedule(_req: Request) -> Response:
    """定时任务状态（v1.8.3）。

    `serve` 是独立进程，控制台通过它写下的心跳文件判断运行状态。
    状态文件不存在/心跳过期都如实返回 `running: false` + `reason`，不猜测。
    """
    return json_response(schedule_state.snapshot())


def metrics(req: Request) -> Response:
    """运行指标（v1.8.3）。

    从最近 N 天的 jsonl 日志聚合成功率、耗时、缓存命中率、token 消耗。
    `success_rate` 可能为 `null`——表示该 Agent 不记录 `done` 事件，
    成功率无从计算（而不是 0%），前端应显示「未知」。
    """
    try:
        days = int(req.q("days") or 7)
    except ValueError:
        days = 7
    return json_response(metrics_service.collect(days=days))


def openapi(_req: Request) -> Response:
    """机器可读的接口清单（v1.8.2，CODE_REVIEW.md F11）。

    路径与方法从路由表内省，因此永远与实现一致。结果进程内缓存。
    """
    global _openapi_cache
    if _openapi_cache is None:
        from ..app import build_router
        from ..openapi import build_openapi

        _openapi_cache = build_openapi(build_router().routes())
    return json_response(_openapi_cache)


def register(router: Router) -> None:
    router.get("/api/health", health)
    router.get("/api/system/config", config)
    router.get("/api/system/overview", overview)
    router.get("/api/system/schedule", schedule)
    router.get("/api/system/metrics", metrics)
    router.get("/api/openapi.json", openapi)
