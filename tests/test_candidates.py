"""候选池（app/candidates.py，design.md §16.3 / Req10、Req11）。"""
from datetime import date, timedelta

from app import candidates


def _repos() -> list[dict]:
    return [
        {"full_name": "vercel/next.js", "description": "The React Framework",
         "language": "JavaScript", "stars": 120000, "stars_today": 300, "topics": ["react"]},
        {"full_name": "jqlang/jq", "description": "Command-line JSON processor",
         "language": "C", "stars": 30000, "stars_today": 50, "topics": ["cli"]},
        {"full_name": "sindresorhus/awesome", "description": "Awesome lists",
         "language": "Markdown", "stars": 300000, "stars_today": 80, "topics": ["awesome"]},
    ]


def test_build_snapshot_tags_every_repo(tmp_path, monkeypatch):
    monkeypatch.setattr(candidates, "CACHE_DIR", tmp_path)
    day = "2026-10-08"
    snap = candidates.build_day_snapshot(_repos(), "trending_page", day)
    assert snap["count"] == 3
    assert snap["date"] == day
    assert snap["source"] == "trending_page"
    for item in snap["items"]:
        assert item["first_seen"] == day
        assert item["last_seen"] == day
        dims = item["dimensions"]
        for key in ("highlight", "learnable", "deployable", "playfulness", "practical_tool"):
            assert key in dims


def test_save_load_and_merge(tmp_path, monkeypatch):
    monkeypatch.setattr(candidates, "CACHE_DIR", tmp_path)
    d1, d2 = "2026-10-07", "2026-10-08"
    candidates.save(d1, candidates.build_day_snapshot(_repos(), "trending_page", d1))
    # 次日只剩两个仓库，其中一个重复
    candidates.save(d2, candidates.build_day_snapshot(_repos()[:2], "trending_page", d2))

    items = candidates.merged_items([d1, d2])
    assert len(items) == 3  # 去重后仍为 3
    nextjs = next(i for i in items if i["full_name"] == "vercel/next.js")
    assert nextjs["first_seen"] == d1
    assert nextjs["last_seen"] == d2
    assert nextjs["days_count"] == 2

    awesome = next(i for i in items if i["full_name"] == "sindresorhus/awesome")
    assert awesome["days_count"] == 1  # 仅首日出现


def test_apply_filters_combined(tmp_path, monkeypatch):
    monkeypatch.setattr(candidates, "CACHE_DIR", tmp_path)
    candidates.save("2026-10-08",
                    candidates.build_day_snapshot(_repos(), "trending_page", "2026-10-08"))
    items = candidates.merged_items()

    assert len(candidates.apply_filters(items, language="C")) == 1
    assert len(candidates.apply_filters(items, min_stars=100000)) == 2
    assert len(candidates.apply_filters(items, q="json")) == 1
    assert len(candidates.apply_filters(items, deployable="no")) == 1
    # 组合条件
    assert len(candidates.apply_filters(items, language="C", min_stars=999999)) == 0


def test_facets_counts(tmp_path, monkeypatch):
    monkeypatch.setattr(candidates, "CACHE_DIR", tmp_path)
    candidates.save("2026-10-08",
                    candidates.build_day_snapshot(_repos(), "trending_page", "2026-10-08"))
    f = candidates.facets(candidates.merged_items())
    assert f["total"] == 3
    assert f["languages"]["JavaScript"] == 1
    assert sum(f["deployable"].values()) == 3
    assert f["stars"]["max"] == 300000
    assert "2026-10-08" in f["days"]


def test_cleanup_removes_expired(tmp_path, monkeypatch):
    monkeypatch.setattr(candidates, "CACHE_DIR", tmp_path)
    old = (date.today() - timedelta(days=30)).isoformat()
    fresh = date.today().isoformat()
    candidates.save(old, candidates.build_day_snapshot(_repos(), "trending_page", old))
    candidates.save(fresh, candidates.build_day_snapshot(_repos(), "trending_page", fresh))

    removed = candidates.cleanup(keep_days=7)
    assert old in removed
    assert candidates.load(old) is None
    assert candidates.load(fresh) is not None


def test_get_item(tmp_path, monkeypatch):
    monkeypatch.setattr(candidates, "CACHE_DIR", tmp_path)
    candidates.save("2026-10-08",
                    candidates.build_day_snapshot(_repos(), "trending_page", "2026-10-08"))
    assert candidates.get_item("jqlang/jq") is not None
    assert candidates.get_item("nope/nope") is None


def test_no_llm_dependency():
    """Req10.5：候选池环节不得引入 LLM 依赖（模块级 import 检查）。"""
    import inspect

    src = inspect.getsource(candidates)
    assert "from .llm" not in src
    assert "import llm" not in src
    assert "LLMClient" not in src
