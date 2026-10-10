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


# ---------------- star 趋势序列（v1.8.3）----------------

def _repo(full_name: str, stars: int) -> dict:
    return {"full_name": full_name, "description": "d", "language": "Python",
            "stars": stars, "stars_today": 1, "topics": []}


def test_star_history_tracks_growth_across_days(tmp_path, monkeypatch):
    """连续 3 天上榜：序列应由旧到新，且与日期逐位对应。"""
    monkeypatch.setattr(candidates, "CACHE_DIR", tmp_path)
    for day, stars in (("2026-10-08", 100), ("2026-10-09", 250), ("2026-10-10", 400)):
        candidates.save(day, candidates.build_day_snapshot([_repo("a/b", stars)], "x", day))

    item = candidates.merged_items()[0]
    assert item["star_history"] == [100, 250, 400]
    assert item["history_days"] == ["2026-10-08", "2026-10-09", "2026-10-10"]
    assert item["star_delta"] == 300


def test_star_history_days_align_with_values(tmp_path, monkeypatch):
    """回归：日期轴必须与数值逐位对应。

    曾用全局日期并集做横轴，导致「隔天上榜」的仓库序列与日期错位。
    """
    monkeypatch.setattr(candidates, "CACHE_DIR", tmp_path)
    candidates.save("2026-10-08", candidates.build_day_snapshot([_repo("a/b", 10)], "x", "2026-10-08"))
    # 10-09 缺席，10-10 又出现
    candidates.save("2026-10-10", candidates.build_day_snapshot([_repo("a/b", 30)], "x", "2026-10-10"))

    item = candidates.merged_items()[0]
    assert item["star_history"] == [10, 30], "缺席日不应补零"
    assert item["history_days"] == ["2026-10-08", "2026-10-10"], "日期轴应跳过缺席日"
    assert len(item["star_history"]) == len(item["history_days"])


def test_star_history_single_point_has_zero_delta(tmp_path, monkeypatch):
    """只上榜一次时无法体现趋势：序列长度 1、Δ=0（前端据此显示「数据不足」）。"""
    monkeypatch.setattr(candidates, "CACHE_DIR", tmp_path)
    candidates.save("2026-10-10", candidates.build_day_snapshot([_repo("a/b", 500)], "x", "2026-10-10"))

    item = candidates.merged_items()[0]
    assert item["star_history"] == [500]
    assert item["star_delta"] == 0


def test_star_history_detects_decline(tmp_path, monkeypatch):
    """star 下降（如被重置/删库）也要如实反映，不能取绝对值。"""
    monkeypatch.setattr(candidates, "CACHE_DIR", tmp_path)
    candidates.save("2026-10-08", candidates.build_day_snapshot([_repo("a/b", 900)], "x", "2026-10-08"))
    candidates.save("2026-10-09", candidates.build_day_snapshot([_repo("a/b", 700)], "x", "2026-10-09"))

    item = candidates.merged_items()[0]
    assert item["star_history"] == [900, 700]
    assert item["star_delta"] == -200


def test_star_history_isolated_per_repo(tmp_path, monkeypatch):
    """多个仓库的序列不能互相污染。"""
    monkeypatch.setattr(candidates, "CACHE_DIR", tmp_path)
    candidates.save("2026-10-08", candidates.build_day_snapshot(
        [_repo("a/one", 10), _repo("b/two", 1000)], "x", "2026-10-08"))
    candidates.save("2026-10-09", candidates.build_day_snapshot(
        [_repo("a/one", 20), _repo("b/two", 2000)], "x", "2026-10-09"))

    by_name = {it["full_name"]: it for it in candidates.merged_items()}
    assert by_name["a/one"]["star_history"] == [10, 20]
    assert by_name["b/two"]["star_history"] == [1000, 2000]
    assert by_name["a/one"]["star_delta"] == 10
    assert by_name["b/two"]["star_delta"] == 1000


def test_star_history_zero_when_stars_missing(tmp_path, monkeypatch):
    """缺失 stars 字段按 0 处理，不应抛异常。"""
    monkeypatch.setattr(candidates, "CACHE_DIR", tmp_path)
    snap = candidates.build_day_snapshot([_repo("a/b", 5)], "x", "2026-10-08")
    snap["items"][0].pop("stars")
    candidates.save("2026-10-08", snap)

    item = candidates.merged_items()[0]
    assert item["star_history"] == [0]

