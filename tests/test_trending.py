"""trending 页面解析与多入口聚合（design.md §6.2 主方案）——离线夹具测试。"""

from app import trending
from app.trending import _merge_into, _rank_repos, fetch_trending, parse_trending_html

HTML = """
<div id="articles">
<article class="Box-row">
  <h2 class="h3 lh-condensed"><a href="/psf/requests" data-hydro-click>requests</a></h2>
  <p class="col-9 color-fg-muted my-1 pr-4">A simple, yet elegant HTTP library.</p>
  <span class="repo-language-color" style="background-color:#3572A5"></span>
  <span itemprop="programmingLanguage">Python</span>
  <a href="/psf/requests/stargazers">52,123</a>
  <a href="/psf/requests/forks">9,876</a>
  <span class="d-inline-block float-sm-right">1,234 stars today</span>
</article>
<article class="Box-row">
  <h2 class="h3 lh-condensed"><a href="/pallets/flask">flask</a></h2>
  <span itemprop="programmingLanguage">Python</span>
  <span class="d-inline-block float-sm-right">567 stars today</span>
</article>
<article class="Box-row">
  <h2><a href="/psf/requests">重复仓库应去重</a></h2>
</article>
<article class="Box-row">
  <h2><a href="/features/copilot">导航链接不是仓库</a></h2>
  <span class="d-inline-block float-sm-right">99 stars today</span>
</article>
<article class="Box-row">
  <h2><a href="/torvalds/linux">linux</a></h2>
</article>
</div>
"""


def test_parse_extracts_repos_in_order():
    items = parse_trending_html(HTML)
    assert [i["full_name"] for i in items] == ["psf/requests", "pallets/flask", "torvalds/linux"]


def test_parse_excludes_navigation_links():
    items = parse_trending_html(HTML)
    assert not any("features" in i["full_name"] for i in items)


def test_parse_stars_today():
    items = parse_trending_html(HTML)
    assert items[0]["stars_today"] == 1234
    assert items[1]["stars_today"] == 567
    assert items[2]["stars_today"] is None


def test_parse_dedupes():
    items = parse_trending_html(HTML)
    assert len(items) == len({i["full_name"] for i in items})


def test_parse_extracts_metadata():
    """v1.7：必须补齐描述/语言/star，否则候选池打标与筛选全部失效。"""
    item = parse_trending_html(HTML)[0]
    assert item["description"] == "A simple, yet elegant HTTP library."
    assert item["language"] == "Python"
    assert item["stars"] == 52123
    assert item["forks"] == 9876
    assert item["html_url"] == "https://github.com/psf/requests"


# ---- 多入口聚合（v1.7） ----


def test_merge_into_dedupes_and_accumulates_sources():
    pool: dict[str, dict] = {}
    _merge_into(pool, [{"full_name": "a/b", "stars_today": 10, "stars": 100}], "daily")
    _merge_into(pool, [{"full_name": "a/b", "stars_today": 30, "stars": 100}], "weekly")
    assert len(pool) == 1
    assert pool["a/b"]["stars_today"] == 30          # 保留更高的今日 star
    assert pool["a/b"]["sources"] == ["daily", "weekly"]


def test_merge_into_fills_missing_fields():
    pool: dict[str, dict] = {}
    _merge_into(pool, [{"full_name": "a/b", "stars_today": 5}], "daily")
    _merge_into(pool, [{"full_name": "a/b", "description": "desc", "language": "Go"}], "weekly")
    assert pool["a/b"]["description"] == "desc"
    assert pool["a/b"]["language"] == "Go"


def test_rank_repos_by_stars_today_then_stars():
    repos = [
        {"full_name": "a", "stars_today": 10, "stars": 999},
        {"full_name": "b", "stars_today": 50, "stars": 1},
        {"full_name": "c", "stars_today": None, "stars": 5000},
        {"full_name": "d", "stars_today": 10, "stars": 5000},
    ]
    order = [r["full_name"] for r in _rank_repos(repos)]
    assert order == ["b", "d", "a", "c"]  # 今日 star 优先，其次总 star


class _FakeClient:
    """按 URL 返回预设页面，用于测试聚合而不发真实请求。"""

    def __init__(self, pages: dict[str, str], fail: set[str] | None = None) -> None:
        self.pages = pages
        self.fail = fail or set()
        self.calls: list[str] = []

    def get_page(self, url: str):
        self.calls.append(url)
        for key in self.fail:
            if key in url:
                raise RuntimeError("boom")
        path = url.replace("https://github.com", "")

        class _R:
            text = self.pages.get(path, "<div></div>")

        return _R()


def _page(*names: str) -> str:
    arts = "".join(
        f'<article class="Box-row"><h2><a href="/{n}">{n}</a></h2>'
        f'<span class="d-inline-block float-sm-right">{i + 1} stars today</span></article>'
        for i, n in enumerate(names)
    )
    return f"<div>{arts}</div>"


def test_fetch_trending_aggregates_and_stops_early():
    client = _FakeClient({
        "/trending?since=daily": _page("a/one", "a/two"),
        "/trending?since=weekly": _page("a/three", "a/one"),
    })
    repos, source = fetch_trending(client, top_n=3)
    assert source == "trending_page"
    assert {r["full_name"] for r in repos} == {"a/one", "a/two", "a/three"}
    # 凑够 3 个即停，不应把后续入口全跑一遍
    assert len(client.calls) == 2


def test_fetch_trending_tolerates_single_source_failure():
    client = _FakeClient(
        {"/trending?since=weekly": _page("b/one")},
        fail={"/trending?since=daily"},
    )
    repos, source = fetch_trending(client, top_n=5)
    assert source == "trending_page"
    assert [r["full_name"] for r in repos] == ["b/one"]


def test_fetch_trending_falls_back_to_search(monkeypatch):
    class _SearchClient:
        def get_page(self, url: str):
            class _R:
                text = "<div></div>"  # 所有入口都解析不出仓库

            return _R()

        def search_repos(self, query: str, per_page: int = 30):
            return [{"full_name": "x/y", "description": "d", "language": "Go",
                     "stargazers_count": 1, "forks_count": 0, "topics": []}]

    repos, source = fetch_trending(_SearchClient(), top_n=5)
    assert source == "search_api"
    assert repos[0]["full_name"] == "x/y"


def test_aggregate_sources_cover_multiple_entries():
    """聚合入口应覆盖日/周/月榜与语言榜，保证池子足够大。"""
    src = trending.AGGREGATE_SOURCES
    assert len(src) >= 6
    assert any("daily" in s for s in src)
    assert any("weekly" in s for s in src)
    assert any("monthly" in s for s in src)
    assert any(s.startswith("/trending/python") for s in src)


def test_enrich_repo_metadata_skips_repos_with_topics():
    calls = []

    class _C:
        def get_repo(self, name):
            calls.append(name)
            return {"topics": ["t"], "description": "d", "language": "Go",
                    "stargazers_count": 1, "forks_count": 0, "license": None}

    repos = [{"full_name": "a/has", "topics": ["x"]}, {"full_name": "a/needs"}]
    filled = trending.enrich_repo_metadata(_C(), repos)
    assert filled == 1
    assert calls == ["a/needs"]  # 已有 topics 的不再请求
    assert repos[1]["topics"] == ["t"]

