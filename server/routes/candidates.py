"""候选仓库路由（design.md §16.7）。

分阶段接口边界（Req12）：
    GET  /api/candidates                列表 + 多条件筛选   —— 零 LLM
    GET  /api/candidates/facets         筛选项与分布        —— 零 LLM
    GET  /api/candidates/{o}/{r}        详情（含维度理由）   —— 零 LLM
    POST /api/candidates/{o}/{r}/preview  **阶段一**：搜索引擎摘要 —— 零 LLM
    POST /api/candidates/{o}/{r}/analyze  **阶段二**：提交 LLM 解析任务
"""
from __future__ import annotations

from app import candidates, classify, search

from ..http import Request, Response, Router, error, json_response
from ..services import task_service


def _int(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except ValueError:
        return None


def list_candidates(req: Request) -> Response:
    """候选列表（Req11）。全部筛选条件即时生效，不调用 LLM。"""
    items = candidates.merged_items()
    filtered = candidates.apply_filters(
        items,
        language=req.q("language"),
        deployable=req.q("deployable"),
        playfulness=req.q("playfulness"),
        practical_tool=req.q("practical_tool"),
        project_type=req.q("project_type"),
        direction=req.q("direction"),
        trend=req.q("trend"),
        min_stars=_int(req.q("min_stars")),
        min_days=_int(req.q("min_days")),
        q=req.q("q"),
        day=req.q("day"),
    )
    try:
        limit = min(max(int(req.q("limit") or 120), 1), 400)
    except ValueError:
        limit = 120
    return json_response({
        "total": len(filtered),
        "pool_total": len(items),
        "items": filtered[:limit],
        "labels": classify.LABELS,
    })


def candidate_facets(_req: Request) -> Response:
    items = candidates.merged_items()
    return json_response({**candidates.facets(items), "labels": classify.LABELS})


def candidate_detail(req: Request) -> Response:
    full_name = f"{req.path_params.get('owner')}/{req.path_params.get('repo')}"
    item = candidates.get_item(full_name)
    if item is None:
        return error(404, f"候选池中没有该仓库：{full_name}", code="CANDIDATE_NOT_FOUND")

    # 详情页补一次目录树，让「是否可部署」判定更准（Req13.2 的判定理由更可靠）
    tree: list[str] = []
    try:
        from app.config import Settings
        from app.github_client import GitHubClient

        client = GitHubClient(token=Settings.load().github_token)
        branch = client.get_repo(full_name).get("default_branch") or "main"
        tree, _ = client.get_tree(full_name, branch)
    except Exception:  # noqa: BLE001 - 拿不到目录树时保留元数据判定结果
        tree = []

    if tree:
        dims = classify.classify(
            item.get("full_name", ""),
            item.get("description"),
            item.get("topics") or [],
            item.get("language"),
            tree=tree,
        )
        item = {**item, "dimensions": dims, "tree_size": len(tree)}

    return json_response({**item, "labels": classify.LABELS})


def preview(req: Request) -> Response:
    """**阶段一**：搜索引擎摘要（Req12.1–12.6）。

    严格不调用 LLM，只做检索结果聚合。
    """
    full_name = f"{req.path_params.get('owner')}/{req.path_params.get('repo')}"
    item = candidates.get_item(full_name) or {}
    description = item.get("description")

    try:
        payload = req.json()
    except ValueError:
        payload = {}
    custom_query = str(payload.get("query") or "").strip()

    outcome = (
        search.search_query(custom_query) if custom_query
        else search.search_repo(full_name, description)
    )
    return json_response({
        **outcome.to_dict(),
        "full_name": full_name,
        "html_url": search.build_repo_url(full_name),
        "stage": "preview",
        "llm_used": False,
    })


def analyze(req: Request) -> Response:
    """**阶段二**：提交完整 LLM 解析任务（Req12.7–12.10）。

    只在用户明确调用该接口时才创建任务；任务在后台线程执行。
    """
    full_name = f"{req.path_params.get('owner')}/{req.path_params.get('repo')}"
    item = candidates.get_item(full_name)
    if item is None:
        return error(404, f"候选池中没有该仓库：{full_name}", code="CANDIDATE_NOT_FOUND")

    task = task_service.service.submit_repo(item.get("html_url") or full_name)
    return json_response({
        **task.to_dict(),
        "stage": "analyze",
        "llm_used": True,
        "hint": "解析在后台进行，可在「任务中心」查看实时日志；完成后到「解读文档」阅读。",
    }, status=202)


def register(router: Router) -> None:
    router.get("/api/candidates", list_candidates)
    router.get("/api/candidates/facets", candidate_facets)
    router.get("/api/candidates/{owner}/{repo}", candidate_detail)
    router.post("/api/candidates/{owner}/{repo}/preview", preview)
    router.post("/api/candidates/{owner}/{repo}/analyze", analyze)
