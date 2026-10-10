"""内容寻址缓存（design.md §8.2）。"""
from datetime import date

from app.cache import Cache, repo_key
from app.contracts import MODULE_KEYS


def _modules(fill: str = "x") -> dict:
    """六模块齐全的 finaldoc.modules。"""
    return {k: fill for k in MODULE_KEYS}


def test_key_depends_on_name_and_sha():
    assert repo_key("a/b", "sha1") == repo_key("a/b", "sha1")
    assert repo_key("a/b", "sha1") != repo_key("a/b", "sha2")
    assert repo_key("a/b", "sha1") != repo_key("a/c", "sha1")


def test_roundtrip(tmp_path):
    c = Cache(tmp_path)
    c.put("psf/requests", "sha-abc", {"modules": _modules()}, "2026-09-27 10:00",
          meta={"stars": 1})
    hit = c.get("psf/requests", "sha-abc")
    assert hit and hit["finaldoc"]["modules"]["intro"] == "x"
    assert hit["meta"] == {"stars": 1}


def test_miss_on_new_commit(tmp_path):
    c = Cache(tmp_path)
    c.put("psf/requests", "sha-abc", {"modules": _modules()}, "2026-09-27 10:00")
    assert c.get("psf/requests", "sha-new") is None  # head_sha 变化即失效（§8.2）


def test_miss_when_module_scheme_changed(tmp_path):
    """v1.5 回归：模块口径变更后，旧缓存（七模块）必须失效，不得复用。

    缓存键只含 full_name + head_sha，不含口径版本；若不校验，
    仓库未更新时会继续吐出七模块的旧解读结果。
    """
    c = Cache(tmp_path)
    legacy = {k: "old" for k in MODULE_KEYS}
    legacy["errors"] = "七模块时代的报错大全"          # 旧口径多出的模块
    c.put("psf/requests", "sha-abc", {"modules": legacy}, "2026-09-27 10:00")
    assert c.get("psf/requests", "sha-abc") is None

    # 缺模块同样视为不兼容
    c.put("psf/requests", "sha-def", {"modules": {"intro": "x"}}, "2026-09-27 10:00")
    assert c.get("psf/requests", "sha-def") is None


def test_internal_keys_ignored_in_schema_check(tmp_path):
    """下划线开头的内部键（如 _project_type）不参与口径比对。"""
    c = Cache(tmp_path)
    mods = _modules()
    mods["_project_type"] = "tool"
    c.put("psf/requests", "sha-abc", {"modules": mods}, "2026-09-27 10:00")
    assert c.get("psf/requests", "sha-abc") is not None


def test_trending_daily_snapshot(tmp_path):
    c = Cache(tmp_path)
    day = date(2026, 9, 27)
    c.put_trending(day, [{"full_name": "a/b"}], source="search_api")
    snap = c.get_trending(day)
    assert snap["source"] == "search_api"              # Req1.6：来源随快照保存
    assert snap["repos"] == [{"full_name": "a/b"}]
    assert c.get_trending(date(2026, 9, 28)) is None   # 跨日必须重取（§8.2 兜底）


def test_trending_legacy_snapshot_compat(tmp_path):
    """修复前的旧格式（裸 list）应兼容读取，来源按 search_api 处理（第三轮缺陷 #1 回归）。"""
    import json

    c = Cache(tmp_path)
    legacy = c.dir / "trending-2026-09-26.json"
    legacy.write_text(json.dumps([{"full_name": "x/y"}]), encoding="utf-8")
    snap = c.get_trending(date(2026, 9, 26))
    assert snap["source"] == "search_api"
    assert snap["repos"] == [{"full_name": "x/y"}]
