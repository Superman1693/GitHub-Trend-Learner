"""搜索引擎接入（app/search.py，design.md §16.8 / Req12）。

只测纯函数与解析逻辑，不发起真实网络请求。
"""
from app import search


def test_build_query_is_exact_name():
    """回归：描述关键词曾污染检索词，导致冷门仓库返回无关结果。"""
    q = search.build_query("morluto/rea", "Reverse engineer anything with agents")
    assert q == '"morluto/rea"'
    assert "Reverse" not in q


def test_search_repo_first_attempt_is_exact_name(monkeypatch):
    """生产路径回归：search_repo 的一级检索词必须复用 build_query 的精确名规则。

    v1.8.2 前 `search_repo` 里另写了一遍 `f'"{full_name}"'`，与 build_query 重复；
    本测试同时锁住「精确名优先」的行为与「只有一处实现」的约束。
    """
    seen: list[str] = []

    def fake_bing(query: str, limit: int, timeout: int):
        seen.append(query)
        return [search.SearchResult("GitHub - a/b", "https://github.com/a/b", "desc", "github.com")]

    monkeypatch.setattr(search, "_bing", fake_bing)
    outcome = search.search_repo("a/b", "noisy description words here")

    assert seen and seen[0] == search.build_query("a/b")
    assert seen[0] == '"a/b"'
    assert outcome.provider == "bing"
    assert "noisy" not in seen[0]


def test_rank_prefers_github_and_name_match():
    results = [
        search.SearchResult("TOP 25 QUOTES BY DMX", "https://azquotes.com/x", "quotes", "azquotes.com"),
        search.SearchResult("GitHub - morluto/rea", "https://github.com/morluto/rea", "desc", "github.com"),
        search.SearchResult("morluto/rea 介绍", "https://blog.example.com/p", "中文介绍", "blog.example.com"),
        search.SearchResult("unrelated page", "https://other.com/x", "nothing", "other.com"),
    ]
    ranked, relevant = search._rank(results, "morluto/rea")
    assert ranked[0].domain == "github.com"     # 仓库主页优先
    assert relevant == 2                        # 两条与仓库名相关
    assert all(r.domain != "azquotes.com" for r in ranked[:2])


def test_rank_keeps_all_when_too_few_relevant():
    """相关结果不足 3 条时保留全部，避免结果页空掉。"""
    results = [
        search.SearchResult("GitHub - a/b", "https://github.com/a/b", "d", "github.com"),
        search.SearchResult("unrelated", "https://x.com/1", "n", "x.com"),
        search.SearchResult("unrelated2", "https://y.com/2", "n", "y.com"),
    ]
    ranked, relevant = search._rank(results, "a/b")
    assert len(ranked) == 3
    assert relevant == 1


def test_unwrap_bing_redirect():
    url = "https://www.bing.com/ck/a?u=a1aHR0cHM6Ly9naXRodWIuY29tL2EvYg&ntb=1"
    unwrapped = search._unwrap_bing(url)
    assert unwrapped.startswith("https://github.com/") or unwrapped == url


def test_outcome_disclaimer_present():
    """Req12.3：阶段一结果必须标注「非 AI 生成」。"""
    outcome = search.SearchOutcome(query="q", provider="bing")
    payload = outcome.to_dict()
    assert "非 AI 生成" in payload["disclaimer"]
    assert payload["provider"] == "bing"


def test_search_result_to_dict():
    r = search.SearchResult("t", "https://a.com", "s", "a.com")
    assert r.to_dict() == {"title": "t", "url": "https://a.com", "snippet": "s", "domain": "a.com"}


def test_build_repo_url():
    assert search.build_repo_url("a/b") == "https://github.com/a/b"


def test_no_llm_import():
    """Req12.2：阶段一模块不得引入 LLM。"""
    import inspect

    src = inspect.getsource(search)
    assert "from .llm" not in src
    assert "LLMClient" not in src
