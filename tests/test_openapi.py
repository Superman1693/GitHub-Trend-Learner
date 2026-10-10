"""接口清单（server/openapi.py）测试。

核心保证：**文档与实现不脱节**——所有路由都必须出现在清单里，
且 API.md 与当前路由表保持同步（漂移会被 CI 拦下）。
"""
from __future__ import annotations

import json

from app import __version__
from server.app import build_router
from server.openapi import SUMMARIES, build_markdown, build_openapi


def _routes():
    return build_router().routes()


def test_every_route_is_documented():
    """每条已注册路由都必须能在 OpenAPI 中找到，且都有中文说明。"""
    doc = build_openapi(_routes())
    for method, pattern in _routes():
        assert pattern in doc["paths"], f"{pattern} 未出现在接口清单中"
        assert method.lower() in doc["paths"][pattern], f"{method} {pattern} 缺失"
        summary = doc["paths"][pattern][method.lower()]["summary"]
        assert summary and summary != pattern, f"{method} {pattern} 缺少中文说明"


def test_summaries_have_no_stale_entries():
    """SUMMARIES 里不能残留已不存在的路由（否则说明路由被删而文档没跟）。"""
    registered = {(m, p) for m, p in _routes()}
    stale = set(SUMMARIES) - registered
    assert not stale, f"以下说明对应的路由已不存在：{sorted(stale)}"


def test_openapi_structure_is_valid():
    doc = build_openapi(_routes())
    assert doc["openapi"].startswith("3.")
    assert doc["info"]["version"] == __version__
    assert doc["paths"], "paths 不能为空"


def test_path_params_are_declared():
    """路径模板里的 {xxx} 必须作为 path 参数声明。"""
    doc = build_openapi(_routes())
    for pattern, ops in doc["paths"].items():
        expected = {seg[1:-1] for seg in pattern.strip("/").split("/")
                    if seg.startswith("{") and seg.endswith("}")}
        if not expected:
            continue
        for op in ops.values():
            declared = {p["name"] for p in op.get("parameters", []) if p["in"] == "path"}
            assert expected <= declared, f"{pattern} 缺少路径参数声明：{expected - declared}"


def test_export_route_declares_binary_response():
    doc = build_openapi(_routes())
    op = doc["paths"]["/api/documents/export"]["get"]
    assert "application/zip" in op["responses"]["200"]["content"]


def test_post_routes_declare_request_body():
    doc = build_openapi(_routes())
    for path in ("/api/tasks", "/api/candidates/{owner}/{repo}/preview"):
        assert "requestBody" in doc["paths"][path]["post"], f"{path} 缺少 requestBody"


def test_markdown_lists_all_routes():
    md = build_markdown(_routes())
    for _, pattern in _routes():
        assert f"`{pattern}`" in md, f"API.md 未包含 {pattern}"
    assert f"共 {len(_routes())} 个接口" in md


def test_api_md_is_in_sync_with_code():
    """漂移守卫：仓库里的 API.md 必须与当前路由表一致。

    改路由后忘了重跑 `python main.py api-doc` 时，本测试会失败并提示。
    """
    from app.config import PROJECT_ROOT

    path = PROJECT_ROOT / "API.md"
    assert path.is_file(), "API.md 不存在，请执行：python main.py api-doc"
    expected = build_markdown(_routes())
    actual = path.read_text(encoding="utf-8")
    assert actual == expected, (
        "API.md 与当前路由表不一致，请重新生成：python main.py api-doc"
    )


def test_openapi_route_returns_json():
    from server.http.request import Request
    from server.routes.system import openapi

    resp = openapi(Request.from_raw("GET", "/api/openapi.json", {}, b""))
    payload = json.loads(resp.body)
    assert payload["info"]["version"] == __version__
    assert "/api/health" in payload["paths"]
