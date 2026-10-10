"""文档路由：产出文档的列表、全文检索、批量导出与详情。"""
from __future__ import annotations

from urllib.parse import quote

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
        hits = document_service.search_documents(keyword)
        # total 是真实命中数，items 才是当前页——两者必须区分，否则前端无法做分页提示
        return json_response({"total": len(hits), "items": hits[:limit], "query": keyword,
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


def export_documents(req: Request) -> Response:
    """批量导出为 ZIP（v1.8，CODE_REVIEW.md F6）。

    `?date=YYYY-MM-DD` 只导出该日；不传则导出全部（受单次上限约束）。
    """
    date = (req.q("date") or "").strip() or None
    if date and not document_service.is_valid_date(date):
        return error(400, "date 格式应为 YYYY-MM-DD", code="INVALID_DATE")

    data, filename, note = document_service.build_export_zip(date)
    if data is None:
        return error(404, note, code="NOTHING_TO_EXPORT")

    # RFC 5987：文件名同时给 ASCII 回退与 UTF-8 形式，兼容各浏览器
    disposition = f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}"
    return Response(
        status=200,
        body=data,
        content_type="application/zip",
        headers={"Content-Disposition": disposition, "Cache-Control": "no-store"},
    )


def register(router: Router) -> None:
    router.get("/api/documents", list_documents)
    router.get("/api/documents/stats", stats)
    router.get("/api/documents/export", export_documents)
    router.get("/api/documents/{date}/{name}", get_document)
