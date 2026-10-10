"""文档路由：产出文档的列表与详情。"""
from __future__ import annotations

from ..http import Request, Response, Router, error, json_response
from ..services import document_service


def list_documents(req: Request) -> Response:
    """文档列表。带 `q` 时执行**全文检索**（v1.8：此前只匹配文件名/标题）。"""
    keyword = (req.q("q") or "").strip()

    if keyword:
        try:
            limit = min(max(int(req.q("limit") or 50), 1), 200)
        except ValueError:
            limit = 50
        hits = document_service.search_documents(keyword, limit=limit)
        return json_response({"total": len(hits), "items": hits, "query": keyword,
                              "full_text": True})

    docs = document_service.list_documents()
    date = req.q("date")
    if date:
        docs = [d for d in docs if d["date"] == date]
    return json_response({"total": len(docs), "items": docs, "full_text": False})


def get_document(req: Request) -> Response:
    date = req.path_params.get("date", "")
    name = req.path_params.get("name", "")
    doc = document_service.load_document(date, name)
    if doc is None:
        return error(404, f"文档不存在：{date}/{name}", code="DOCUMENT_NOT_FOUND")
    return json_response(doc)


def stats(_req: Request) -> Response:
    return json_response(document_service.stats())


def register(router: Router) -> None:
    router.get("/api/documents", list_documents)
    router.get("/api/documents/stats", stats)
    router.get("/api/documents/{date}/{name}", get_document)
