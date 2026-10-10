"""候选收藏（app/favorites.py + 路由）测试。

收藏是**用户数据**，比缓存更不可丢：
- 必须原子写入，进程中断不能写坏文件；
- 不能被缓存清理误删（候选池只留 7 天，但收藏要长期保留）；
- 已从榜单消失的仓库仍要能列出，否则用户会以为「收藏丢了」。
"""
from __future__ import annotations

import json

import pytest

from app import favorites
from server.http.request import Request
from server.routes import candidates as routes


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(favorites, "CACHE_DIR", tmp_path)
    return tmp_path


# ---------------- 基础读写 ----------------

def test_add_then_is_favorited(store):
    assert favorites.add("a/b") is True
    assert favorites.is_favorited("a/b") is True
    assert favorites.names() == {"a/b"}


def test_add_is_idempotent(store):
    """重复收藏不应刷新时间，也不应报错。"""
    assert favorites.add("a/b") is True
    assert favorites.add("a/b") is False
    assert favorites.names() == {"a/b"}


def test_remove(store):
    favorites.add("a/b")
    assert favorites.remove("a/b") is True
    assert favorites.remove("a/b") is False
    assert favorites.names() == set()


def test_toggle_returns_new_state(store):
    assert favorites.toggle("a/b") is True
    assert favorites.toggle("a/b") is False
    assert favorites.toggle("a/b") is True


@pytest.mark.parametrize("bad", ["", "   ", "no-slash", None])
def test_add_rejects_invalid_names(store, bad):
    assert favorites.add(bad) is False
    assert favorites.names() == set()


def test_add_strips_whitespace(store):
    favorites.add("  a/b  ")
    assert favorites.names() == {"a/b"}


def test_records_added_at_and_note(store):
    favorites.add("a/b", note="值得研究")
    data = favorites.load_all()
    assert data["a/b"]["note"] == "值得研究"
    assert len(data["a/b"]["added_at"]) >= 16     # YYYY-MM-DD HH:MM


# ---------------- 健壮性 ----------------

def test_missing_file_returns_empty(store):
    assert favorites.load_all() == {}
    assert favorites.names() == set()


def test_corrupted_file_does_not_raise(store):
    """文件被写坏时不能让整个发现页崩掉。"""
    (store / favorites.FILENAME).write_text("{不是合法 JSON", encoding="utf-8")
    assert favorites.load_all() == {}


def test_non_dict_json_returns_empty(store):
    (store / favorites.FILENAME).write_text("[1, 2, 3]", encoding="utf-8")
    assert favorites.load_all() == {}


def test_write_is_atomic_no_temp_leftover(store):
    favorites.add("a/b")
    leftovers = [p.name for p in store.iterdir() if p.suffix == ".tmp"]
    assert leftovers == [], f"残留临时文件: {leftovers}"


def test_not_pruned_by_cache_maintenance(store):
    """回归：缓存清理只能删 repo-*/trending-*/translations，不能碰收藏。"""
    from app import maintenance

    favorites.add("a/b")
    (store / "repo-abc.json").write_text("{}", encoding="utf-8")
    (store / "trending-2020-01-01.json").write_text("{}", encoding="utf-8")

    maintenance.prune_cache(store, repo_keep_days=0, trending_keep_days=0)

    assert favorites.is_favorited("a/b") is True, "收藏被缓存清理误删了"
    assert not (store / "repo-abc.json").exists(), "旧缓存应被清理"


# ---------------- 与候选池集成 ----------------

def test_merged_items_marks_favorited(store, monkeypatch):
    from app import candidates

    monkeypatch.setattr(candidates, "CACHE_DIR", store)
    candidates.save("2026-10-10", candidates.build_day_snapshot(
        [{"full_name": "a/b", "description": "d", "stars": 1, "topics": []}], "x", "2026-10-10"))
    favorites.add("a/b")

    item = candidates.merged_items()[0]
    assert item["favorited"] is True


def test_merged_items_unfavorited_by_default(store, monkeypatch):
    from app import candidates

    monkeypatch.setattr(candidates, "CACHE_DIR", store)
    candidates.save("2026-10-10", candidates.build_day_snapshot(
        [{"full_name": "a/b", "description": "d", "stars": 1, "topics": []}], "x", "2026-10-10"))

    assert candidates.merged_items()[0]["favorited"] is False


def test_filter_by_favorited(store):
    items = [{"full_name": "a/b", "favorited": True}, {"full_name": "c/d", "favorited": False}]
    assert [i["full_name"] for i in candidates_filter(items, favorited=True)] == ["a/b"]
    assert [i["full_name"] for i in candidates_filter(items, favorited=False)] == ["c/d"]
    assert len(candidates_filter(items, favorited=None)) == 2


def candidates_filter(items, **kw):
    from app.candidates import apply_filters

    return apply_filters(items, **kw)


# ---------------- 路由层 ----------------

def _req(path: str, params: dict | None = None) -> Request:
    req = Request.from_raw("GET", path, {}, b"")
    if params:
        req.path_params = params
    return req


def _payload(resp) -> dict:
    return json.loads(resp.body)


def test_route_favorite_returns_201_on_first_add(store):
    resp = routes.favorite(_req("/api/candidates/a/b/favorite", {"owner": "a", "repo": "b"}))
    assert resp.status == 201
    assert _payload(resp) == {"full_name": "a/b", "favorited": True,
                              "changed": True, "total": 1}


def test_route_favorite_returns_200_when_already_added(store):
    routes.favorite(_req("/x", {"owner": "a", "repo": "b"}))
    resp = routes.favorite(_req("/x", {"owner": "a", "repo": "b"}))
    assert resp.status == 200
    assert _payload(resp)["changed"] is False


def test_route_unfavorite(store):
    routes.favorite(_req("/x", {"owner": "a", "repo": "b"}))
    resp = routes.unfavorite(_req("/x", {"owner": "a", "repo": "b"}))
    assert resp.status == 200
    assert _payload(resp)["favorited"] is False
    assert _payload(resp)["total"] == 0


def test_route_list_marks_repos_that_left_the_pool(store, monkeypatch):
    """已从候选池消失的收藏仍要列出，并标记 in_pool=false。"""
    from app import candidates

    monkeypatch.setattr(candidates, "merged_items", lambda: [])
    favorites.add("gone/repo")

    payload = _payload(routes.favorite_list(_req("/api/candidates/favorites")))
    assert payload["total"] == 1
    item = payload["items"][0]
    assert item["full_name"] == "gone/repo"
    assert item["in_pool"] is False
    assert item["html_url"] == "https://github.com/gone/repo"


def test_route_list_enriches_from_pool(store, monkeypatch):
    from app import candidates

    monkeypatch.setattr(candidates, "merged_items", lambda: [{
        "full_name": "a/b", "html_url": "https://github.com/a/b", "stars": 99,
        "language": "Python", "description": "d", "description_zh": "中文",
    }])
    favorites.add("a/b")

    item = _payload(routes.favorite_list(_req("/api/candidates/favorites")))["items"][0]
    assert item["in_pool"] is True
    assert item["stars"] == 99
    assert item["description_zh"] == "中文"


def test_route_list_newest_first(store):
    favorites.add("old/one")
    favorites.add("new/two")
    # 手工改写 added_at 以稳定排序
    data = favorites.load_all()
    data["old/one"]["added_at"] = "2026-01-01 00:00"
    data["new/two"]["added_at"] = "2026-12-31 23:59"
    (store / favorites.FILENAME).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    names = [i["full_name"] for i in
             _payload(routes.favorite_list(_req("/x")))["items"]]
    assert names == ["new/two", "old/one"]


def test_favorite_routes_registered():
    from server.app import build_router

    routes_map = {(m, p) for m, p in build_router().routes()}
    assert ("POST", "/api/candidates/{owner}/{repo}/favorite") in routes_map
    assert ("DELETE", "/api/candidates/{owner}/{repo}/favorite") in routes_map
    assert ("GET", "/api/candidates/favorites") in routes_map


def test_bool_helper_three_states():
    assert routes._bool(None) is None
    assert routes._bool("") is None
    assert routes._bool("true") is True
    assert routes._bool("1") is True
    assert routes._bool("false") is False
    assert routes._bool("0") is False
