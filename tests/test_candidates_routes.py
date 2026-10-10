"""候选仓库路由（server/routes/candidates.py）测试。

此前覆盖率仅 30%。这里是「两阶段解析」的 HTTP 边界：
- 阶段一（preview）必须**零 LLM 调用**，且要明确标注非 AI 生成；
- 阶段二（analyze）只在用户明确点击时创建任务。
这条边界一旦被破坏，用户会在「只是看看」时被消耗 LLM 额度，所以必须锁住。

候选池与搜索引擎均用假实现替换，不读真实缓存、不触网。
"""
from __future__ import annotations

import json

import pytest

from app import classify, search
from server.http.request import Request
from server.routes import candidates as routes


def _req(path: str, body: bytes = b"", params: dict | None = None) -> Request:
    req = Request.from_raw("GET", path, {}, body)
    if params:
        req.path_params = params
    return req


def _payload(resp) -> dict:
    return json.loads(resp.body)


_ITEM = {
    "full_name": "a/b",
    "html_url": "https://github.com/a/b",
    "description": "演示仓库",
    "description_zh": "演示仓库（中文）",
    "language": "Python",
    "stars": 100,
    "topics": ["cli"],
    "dimensions": classify.classify("a/b", "演示仓库", ["cli"], "Python"),
}


@pytest.fixture
def pool(monkeypatch):
    """把候选池替换为固定数据。"""
    monkeypatch.setattr(routes.candidates, "merged_items", lambda: [_ITEM])
    monkeypatch.setattr(routes.candidates, "get_item",
                        lambda full_name: _ITEM if full_name == "a/b" else None)
    monkeypatch.setattr(routes.candidates, "facets",
                        lambda items: {"total": len(items), "languages": {"Python": 1}})
    return _ITEM


# ---------------- 列表 ----------------

def test_list_returns_items_and_labels(pool):
    resp = routes.list_candidates(_req("/api/candidates"))
    assert resp.status == 200
    payload = _payload(resp)
    assert payload["total"] == 1
    assert payload["pool_total"] == 1
    assert payload["items"][0]["full_name"] == "a/b"
    assert payload["labels"]["deployable"]["yes"] == "可部署"


def test_list_clamps_limit(monkeypatch, pool):
    """limit 必须被钳制在 1–400，防止一次拉爆前端。"""
    monkeypatch.setattr(routes.candidates, "apply_filters", lambda items, **kw: items * 5)
    resp = routes.list_candidates(_req("/api/candidates?limit=99999"))
    assert len(_payload(resp)["items"]) <= 400


def test_list_falls_back_on_invalid_limit(monkeypatch, pool):
    monkeypatch.setattr(routes.candidates, "apply_filters", lambda items, **kw: items * 200)
    resp = routes.list_candidates(_req("/api/candidates?limit=abc"))
    assert resp.status == 200
    assert len(_payload(resp)["items"]) == 120, "非法 limit 应回落默认值"


def test_list_passes_filters_through(monkeypatch, pool):
    seen: dict = {}

    def fake_filters(items, **kwargs):
        seen.update(kwargs)
        return items

    monkeypatch.setattr(routes.candidates, "apply_filters", fake_filters)
    routes.list_candidates(_req(
        "/api/candidates?language=Python&trend=rising&min_stars=10&min_days=2&direction=AI"))

    assert seen["language"] == "Python"
    assert seen["trend"] == "rising"
    assert seen["min_stars"] == 10
    assert seen["min_days"] == 2
    assert seen["direction"] == "AI"


def test_list_int_helper_handles_blank_and_bad():
    assert routes._int(None) is None
    assert routes._int("") is None
    assert routes._int("7") == 7
    assert routes._int("abc") is None


# ---------------- facets ----------------

def test_facets_includes_labels(pool):
    payload = _payload(routes.candidate_facets(_req("/api/candidates/facets")))
    assert payload["total"] == 1
    assert "project_type" in payload["labels"]


# ---------------- 详情 ----------------

def test_detail_404_when_not_in_pool(pool):
    resp = routes.candidate_detail(_req("/api/candidates/x/y",
                                        params={"owner": "x", "repo": "y"}))
    assert resp.status == 404
    assert _payload(resp)["error"]["code"] == "CANDIDATE_NOT_FOUND"


def test_detail_enriches_dimensions_when_tree_available(monkeypatch, pool):
    """拿到目录树时应重算维度，让「是否可部署」更准（Req13.2）。"""

    class FakeClient:
        def get_repo(self, full_name):
            return {"default_branch": "main"}

        def get_tree(self, full_name, branch):
            return (["Dockerfile", "requirements.txt"], False)

    monkeypatch.setattr(routes, "_client", lambda: FakeClient())

    payload = _payload(routes.candidate_detail(
        _req("/api/candidates/a/b", params={"owner": "a", "repo": "b"})))

    assert payload["tree_size"] == 2
    assert payload["dimensions"]["deployable"] == "yes"
    assert "labels" in payload


def test_detail_falls_back_to_metadata_when_github_fails(monkeypatch, pool):
    """拿不到目录树时必须保留元数据判定结果，不能 500。"""

    class BoomClient:
        def get_repo(self, full_name):
            raise RuntimeError("api down")

    monkeypatch.setattr(routes, "_client", lambda: BoomClient())

    resp = routes.candidate_detail(_req("/api/candidates/a/b",
                                        params={"owner": "a", "repo": "b"}))
    assert resp.status == 200
    payload = _payload(resp)
    assert "tree_size" not in payload, "取树失败时不应写入 tree_size"


# ---------------- 阶段一：preview ----------------

def test_preview_uses_repo_search_and_declares_no_llm(monkeypatch, pool):
    captured: dict = {}

    def fake_search_repo(full_name, description=None, **kw):
        captured["full_name"] = full_name
        captured["description"] = description
        return search.SearchOutcome(query=full_name, provider="bing",
                                    results=[search.SearchResult("t", "https://x.com", "s", "x.com")])

    monkeypatch.setattr(routes.search, "search_repo", fake_search_repo)
    resp = routes.preview(_req("/api/candidates/a/b/preview",
                               params={"owner": "a", "repo": "b"}))

    assert resp.status == 200
    payload = _payload(resp)
    assert payload["llm_used"] is False, "阶段一绝不能调用 LLM"
    assert payload["stage"] == "preview"
    assert payload["html_url"] == "https://github.com/a/b"
    assert "非 AI 生成" in payload["disclaimer"]
    assert captured["full_name"] == "a/b"
    assert captured["description"] == "演示仓库"


def test_preview_uses_custom_query_when_provided(monkeypatch, pool):
    monkeypatch.setattr(routes.search, "search_query",
                        lambda q: search.SearchOutcome(query=q, provider="bing"))
    monkeypatch.setattr(routes.search, "search_repo",
                        lambda *a, **k: pytest.fail("有自定义关键词时不应走仓库检索"))

    resp = routes.preview(_req("/api/candidates/a/b/preview",
                               body=json.dumps({"query": "自定义词"}).encode(),
                               params={"owner": "a", "repo": "b"}))
    assert _payload(resp)["query"] == "自定义词"


def test_preview_tolerates_invalid_json_body(monkeypatch, pool):
    monkeypatch.setattr(routes.search, "search_repo",
                        lambda *a, **k: search.SearchOutcome(query="a/b", provider="bing"))
    resp = routes.preview(_req("/api/candidates/a/b/preview", body=b"{not json",
                               params={"owner": "a", "repo": "b"}))
    assert resp.status == 200, "请求体非法时应退回默认检索，而不是报错"


def test_preview_works_for_repo_not_in_pool(monkeypatch, pool):
    """未入池的仓库也应能预览（description 为空即可）。"""
    monkeypatch.setattr(routes.search, "search_repo",
                        lambda *a, **k: search.SearchOutcome(query="x/y", provider="bing"))
    resp = routes.preview(_req("/api/candidates/x/y/preview",
                               params={"owner": "x", "repo": "y"}))
    assert resp.status == 200


# ---------------- 阶段二：analyze ----------------

def test_analyze_404_when_not_in_pool(pool):
    resp = routes.analyze(_req("/api/candidates/x/y/analyze",
                               params={"owner": "x", "repo": "y"}))
    assert resp.status == 404
    assert _payload(resp)["error"]["code"] == "CANDIDATE_NOT_FOUND"


def test_analyze_submits_task_and_marks_llm_used(monkeypatch, pool):
    submitted: list[str] = []

    class FakeTask:
        def to_dict(self):
            return {"task_id": "t1", "kind": "repo", "status": "pending"}

    monkeypatch.setattr(routes.task_service.service, "submit_repo",
                        lambda url: submitted.append(url) or FakeTask())

    resp = routes.analyze(_req("/api/candidates/a/b/analyze",
                               params={"owner": "a", "repo": "b"}))

    assert resp.status == 202
    payload = _payload(resp)
    assert payload["llm_used"] is True, "阶段二必须明确标注会调用 LLM"
    assert payload["stage"] == "analyze"
    assert payload["task_id"] == "t1"
    assert submitted == ["https://github.com/a/b"], "应提交仓库链接而不是 full_name"


def test_analyze_falls_back_to_full_name_when_html_url_missing(monkeypatch):
    item = {**_ITEM, "html_url": ""}
    monkeypatch.setattr(routes.candidates, "get_item", lambda _n: item)
    submitted: list[str] = []

    class FakeTask:
        def to_dict(self):
            return {"task_id": "t1"}

    monkeypatch.setattr(routes.task_service.service, "submit_repo",
                        lambda url: submitted.append(url) or FakeTask())

    routes.analyze(_req("/api/candidates/a/b/analyze", params={"owner": "a", "repo": "b"}))
    assert submitted == ["a/b"]


# ---------------- 路由注册 ----------------

def test_all_candidate_routes_registered():
    from server.app import build_router

    paths = {p for _, p in build_router().routes()}
    for expected in ("/api/candidates", "/api/candidates/facets",
                     "/api/candidates/{owner}/{repo}",
                     "/api/candidates/{owner}/{repo}/preview",
                     "/api/candidates/{owner}/{repo}/analyze"):
        assert expected in paths
