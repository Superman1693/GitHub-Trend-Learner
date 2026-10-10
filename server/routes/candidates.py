"""候选仓库路由（design.md §16.7）。

分阶段接口边界（Req12）：
    GET  /api/candidates                列表 + 多条件筛选   —— 零 LLM
    GET  /api/candidates/facets         筛选项与分布        —— 零 LLM
    GET  /api/candidates/{o}/{r}        详情（含维度理由）   —— 零 LLM
    POST /api/candidates/{o}/{r}/preview  **阶段一**：搜索引擎摘要 —— 零 LLM
    POST /api/candidates/{o}/{r}/analyze  **阶段二**：提交 LLM 解析任务
"""
from __future__ import annotations

import threading

from app import candidates, classify, favorites, search
from app.config import Settings
from app.github_client import GitHubClient

from ..http import Request, Response, Router, error, json_response
from ..services import task_service

# 进程级复用的 GitHub 客户端（v1.8.2，CODE_REVIEW.md B3）。
# 此前每次详情请求都新建 GitHubClient（即新的 requests.Session），
# 既无法复用连接，也白白重解析一次 .env。
_CLIENT: GitHubClient | None = None
_CLIENT_LOCK = threading.Lock()


def _client() -> GitHubClient:
    global _CLIENT
    if _CLIENT is None:
        with _CLIENT_LOCK:
            if _CLIENT is None:
                _CLIENT = GitHubClient(token=Settings.load().github_token)
    return _CLIENT


def _bool(value: str | None) -> bool | None:
    """三态解析：未传 -> None（不筛选）；1/true/yes -> True；0/false/no -> False。"""
    if value in (None, ""):
        return None
    return value.strip().lower() in ("1", "true", "yes", "on")


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
        favorited=_bool(req.q("favorited")),
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
        client = _client()
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


def favorite(req: Request) -> Response:
    """收藏候选仓库（v1.8.3）。

    候选池只保留 7 天快照，用户看中的仓库若不收藏，过几天就从榜单消失了。
    这里只记录 full_name，元信息仍从候选池实时取，避免数据双份不一致。
    """
    full_name = f"{req.path_params.get('owner')}/{req.path_params.get('repo')}"
    added = favorites.add(full_name)
    return json_response({
        "full_name": full_name,
        "favorited": True,
        "changed": added,
        "total": len(favorites.names()),
    }, status=201 if added else 200)


def unfavorite(req: Request) -> Response:
    full_name = f"{req.path_params.get('owner')}/{req.path_params.get('repo')}"
    removed = favorites.remove(full_name)
    return json_response({
        "full_name": full_name,
        "favorited": False,
        "changed": removed,
        "total": len(favorites.names()),
    })


def favorite_list(_req: Request) -> Response:
    """收藏清单。已从候选池消失的仓库也会列出（`in_pool: false`），

    避免用户以为「收藏丢了」——它们只是不再上榜，仍可点击深入解析。
    """
    data = favorites.load_all()
    pool = {it["full_name"]: it for it in candidates.merged_items()}
    items = []
    for name, meta in sorted(data.items(), key=lambda kv: kv[1].get("added_at", ""), reverse=True):
        entry = pool.get(name)
        items.append({
            "full_name": name,
            "html_url": (entry or {}).get("html_url") or search.build_repo_url(name),
            "stars": (entry or {}).get("stars"),
            "language": (entry or {}).get("language"),
            "description_zh": (entry or {}).get("description_zh"),
            "description": (entry or {}).get("description"),
            "added_at": meta.get("added_at"),
            "note": meta.get("note") or "",
            "in_pool": entry is not None,
        })
    return json_response({"total": len(items), "items": items})


def register(router: Router) -> None:
    router.get("/api/candidates", list_candidates)
    router.get("/api/candidates/facets", candidate_facets)
    router.get("/api/candidates/favorites", favorite_list)
    router.get("/api/candidates/{owner}/{repo}", candidate_detail)
    router.post("/api/candidates/{owner}/{repo}/preview", preview)
    router.post("/api/candidates/{owner}/{repo}/analyze", analyze)
    router.post("/api/candidates/{owner}/{repo}/favorite", favorite)
    router.delete("/api/candidates/{owner}/{repo}/favorite", unfavorite)
