"""搜索引擎解析（app/search.py）测试。

此前覆盖率 61%，未覆盖的正是 `_bing` 的 HTML 解析与降级链——
Bing 返回结构一变、正则写错，表现是「搜索结果为空」或「链接指错」，
而且**不会报错**，属于最难发现的一类缺陷。

用固定的 HTML 片段驱动解析，不触网。
"""
from __future__ import annotations

import base64
import json

import pytest

from app import search
from app.search import SearchResult

# ---------------- 基础工具 ----------------

def test_clean_strips_tags_and_unescapes():
    assert search._clean("<b>你好</b> &amp; 世界") == "你好 & 世界"


def test_clean_handles_empty():
    assert search._clean("") == ""
    assert search._clean(None) == ""


@pytest.mark.parametrize("url,expected", [
    ("https://www.example.com/a", "example.com"),
    ("https://github.com/a/b", "github.com"),
    ("http://sub.example.com:8080/x", "sub.example.com:8080"),
])
def test_domain_extraction(url, expected):
    assert search._domain(url) == expected


def test_domain_returns_empty_on_garbage():
    assert search._domain("not a url") == ""


def test_unwrap_bing_redirect():
    """Bing 部分结果走 /ck/a?u=a1<base64url> 跳转链，必须还原真实地址。"""
    real = "https://example.com/real-page"
    token = base64.urlsafe_b64encode(real.encode()).decode().rstrip("=")
    wrapped = f"https://www.bing.com/ck/a?!&&p=x&u=a1{token}&ntb=1"
    assert search._unwrap_bing(wrapped) == real


def test_unwrap_bing_leaves_plain_url_untouched():
    plain = "https://example.com/direct"
    assert search._unwrap_bing(plain) == plain


def test_unwrap_bing_falls_back_on_bad_base64():
    bad = "https://www.bing.com/ck/a?u=a1!!!not-base64!!!"
    assert search._unwrap_bing(bad) == bad


def test_desc_words_takes_first_three_ascii_tokens():
    assert search._desc_words("Reverse engineer anything with agents") == "Reverse engineer anything"
    assert search._desc_words(None) == ""
    assert search._desc_words("") == ""


# ---------------- _bing HTML 解析 ----------------

_BING_HTML = """
<html><body><ol id="b_results">
<li class="b_algo">
  <h2><a href="https://github.com/a/b">GitHub - a/b</a></h2>
  <p>一个用于演示的仓库 &amp; 示例</p>
</li>
<li class="b_algo">
  <h2><a href="https://www.bing.com/ck/a?u=a1{TOKEN}">博客介绍</a></h2>
  <p>中文介绍页</p>
</li>
<li class="b_algo">
  <h2><a href="javascript:void(0)">无效链接</a></h2>
  <p>应被跳过</p>
</li>
</ol></body></html>
"""


class _Resp:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return json.loads(self.text)


def _with_token() -> str:
    real = "https://blog.example.com/post"
    token = base64.urlsafe_b64encode(real.encode()).decode().rstrip("=")
    return _BING_HTML.replace("{TOKEN}", token)


def test_bing_parses_blocks_and_skips_invalid_links(monkeypatch):
    monkeypatch.setattr(search._SESSION, "get", lambda *a, **k: _Resp(_with_token()))
    results = search._bing("a/b", 10, 5)

    assert len(results) == 2, "javascript: 链接应被跳过"
    assert results[0].title == "GitHub - a/b"
    assert results[0].url == "https://github.com/a/b"
    assert results[0].domain == "github.com"
    assert "示例" in results[0].snippet, "HTML 实体应被还原"
    assert results[1].url == "https://blog.example.com/post", "跳转链应被还原"


def test_bing_respects_limit(monkeypatch):
    monkeypatch.setattr(search._SESSION, "get", lambda *a, **k: _Resp(_with_token()))
    assert len(search._bing("a/b", 1, 5)) == 1


def test_bing_returns_empty_on_unexpected_markup(monkeypatch):
    """Bing 改版导致结构不匹配时应返回空列表，而不是抛异常。"""
    monkeypatch.setattr(search._SESSION, "get", lambda *a, **k: _Resp("<html>全新结构</html>"))
    assert search._bing("a/b", 10, 5) == []


# ---------------- _rank ----------------

def test_rank_prefers_github_and_name_match():
    results = [
        SearchResult("TOP 25 QUOTES", "https://azquotes.com/x", "quotes", "azquotes.com"),
        SearchResult("GitHub - morluto/rea", "https://github.com/morluto/rea", "desc", "github.com"),
        SearchResult("morluto/rea 介绍", "https://blog.example.com/p", "中文介绍", "blog.example.com"),
        SearchResult("unrelated", "https://other.com/x", "nothing", "other.com"),
    ]
    ranked, relevant = search._rank(results, "morluto/rea")
    assert ranked[0].domain == "github.com"
    assert relevant == 2
    assert all(r.domain != "azquotes.com" for r in ranked[:2])


def test_rank_returns_all_when_too_few_relevant():
    results = [SearchResult("x", "https://x.com/1", "", "x.com") for _ in range(3)]
    ranked, relevant = search._rank(results, "zz/yy")
    assert len(ranked) == 3
    assert relevant == 0


# ---------------- 降级链 ----------------

def _outcome_provider(monkeypatch, bing_impl, github_impl):
    monkeypatch.setattr(search, "_bing", bing_impl)
    monkeypatch.setattr(search, "_github", github_impl)


def test_search_repo_uses_bing_first(monkeypatch):
    _outcome_provider(
        monkeypatch,
        lambda q, limit, timeout: [SearchResult("GitHub - a/b", "https://github.com/a/b", "d", "github.com")],
        lambda *a: pytest.fail("Bing 有结果时不应走 GitHub 兜底"),
    )
    out = search.search_repo("a/b", "desc")
    assert out.provider == "bing" and not out.degraded


def test_search_repo_falls_back_to_github_when_bing_empty(monkeypatch):
    _outcome_provider(
        monkeypatch,
        lambda q, limit, timeout: [],
        lambda full_name, limit, timeout: [SearchResult("a/b", "https://github.com/a/b", "d", "github.com")],
    )
    out = search.search_repo("a/b", "desc")
    assert out.provider == "github"
    assert out.degraded is True
    assert "改用 GitHub 搜索" in out.note


def test_search_repo_degrades_gracefully_when_all_fail(monkeypatch):
    def boom(*_a):
        raise RuntimeError("network down")

    _outcome_provider(monkeypatch, boom, boom)
    out = search.search_repo("a/b", "desc")
    assert out.provider == "none"
    assert out.results == []
    assert out.degraded is True
    assert "均不可用" in out.note


def test_search_repo_marks_broad_match_when_nothing_relevant(monkeypatch):
    _outcome_provider(
        monkeypatch,
        lambda q, limit, timeout: [SearchResult("无关页", "https://x.com/1", "", "x.com")],
        lambda *a: [],
    )
    out = search.search_repo("a/b", "desc")
    assert out.degraded is True
    assert "宽泛匹配" in out.note


def test_search_query_returns_none_provider_on_failure(monkeypatch):
    monkeypatch.setattr(search, "_bing", lambda *a: (_ for _ in ()).throw(RuntimeError("x")))
    out = search.search_query("任意关键词")
    assert out.provider == "none" and out.degraded is True


def test_search_query_returns_bing_results(monkeypatch):
    monkeypatch.setattr(search, "_bing",
                        lambda *a: [SearchResult("t", "https://x.com", "s", "x.com")])
    out = search.search_query("关键词")
    assert out.provider == "bing" and len(out.results) == 1


# ---------------- 输出结构 ----------------

def test_outcome_to_dict_includes_disclaimer():
    out = search.SearchOutcome(query="q", provider="bing")
    payload = out.to_dict()
    assert payload["disclaimer"] == "以下为搜索引擎返回的原始结果，非 AI 生成内容。"
    assert json.dumps(payload, ensure_ascii=False)


def test_github_fallback_uses_token_when_configured(monkeypatch):
    captured = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured["headers"] = headers or {}
        return _Resp(json.dumps({"items": [{"full_name": "a/b",
                                            "html_url": "https://github.com/a/b",
                                            "description": "d"}]}))

    monkeypatch.setattr(search._SESSION, "get", fake_get)

    # `_github` 内部 `from .config import Settings` 后调用 `Settings.load()`，
    # 因此补丁要打在 app.config 上，且假类需提供 load()
    import app.config as app_config

    class _FakeSettings:
        github_token = "tk"

        @classmethod
        def load(cls, env_path=None):
            return cls()

    monkeypatch.setattr(app_config, "Settings", _FakeSettings)

    results = search._github("a/b", limit=5, timeout=5)
    assert captured["headers"]["Authorization"] == "Bearer tk"
    assert results[0].domain == "github.com"


def test_github_fallback_omits_authorization_without_token(monkeypatch):
    captured = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured["headers"] = headers or {}
        return _Resp(json.dumps({"items": []}))

    monkeypatch.setattr(search._SESSION, "get", fake_get)
    import app.config as app_config

    class _FakeSettings:
        github_token = None

        @classmethod
        def load(cls, env_path=None):
            return cls()

    monkeypatch.setattr(app_config, "Settings", _FakeSettings)

    search._github("a/b", limit=5, timeout=5)
    assert "Authorization" not in captured["headers"]


# ---------------- 相关性判定：短 owner 名误命中（v1.9.0 真实缺陷）----------------

def test_rank_owner_only_match_is_not_relevant():
    """回归：`psf/requests` 的 owner "psf" 命中了光学名词「PSF」，把 8 条光学文章
    算成相关结果，degraded 误报为 False —— 用户会把这些文章当成该仓库的摘要。

    修正后：owner 命中只作排序加分，不作为「相关」判据。
    """
    optics = [
        SearchResult("光学成像系统中的点扩散函数（PSF）：诞生、物理机制", "https://zhuanlan.zhihu.com/p/1", "PSF 详解", "zhuanlan.zhihu.com"),
        SearchResult("点扩散函数 point spread function (PSF)", "https://blog.csdn.net/x", "PSF 与去卷积", "blog.csdn.net"),
        SearchResult("点扩散函数_百度百科", "https://baike.baidu.com/item/PSF", "PSF 定义", "baike.baidu.com"),
    ]
    ranked, relevant = search._rank(optics, "psf/requests")
    assert relevant == 0, "仅 owner 命中不应算相关"
    assert len(ranked) == 3, "相关数为 0 时仍返回全部结果（避免面板空掉）"


def test_rank_repo_name_match_is_relevant():
    """仓库名命中仍是强信号。"""
    results = [
        SearchResult("GitHub - psf/requests", "https://github.com/psf/requests", "HTTP library", "github.com"),
        SearchResult("requests 库入门", "https://blog.example.com/r", "requests 教程", "blog.example.com"),
        SearchResult("python requests 用法", "https://x.com/r", "requests 详解", "x.com"),
    ]
    _, relevant = search._rank(results, "psf/requests")
    assert relevant == 3


def test_rank_full_slug_match_counts_for_short_repo_names():
    """短仓库名（jq）单独出现太易误命中，要求完整 slug。"""
    results = [
        SearchResult("Minecraft 官网", "https://minecraft.net", "我的世界", "minecraft.net"),
        SearchResult("jqlang/jq 使用指南", "https://blog.example.com/jq", "命令行 JSON", "blog.example.com"),
        SearchResult("jqlang/jq 教程", "https://x.com/jq", "jq 详解", "x.com"),
    ]
    _, relevant = search._rank(results, "jqlang/jq")
    assert relevant == 2, "完整 slug 命中的两条应算相关，Minecraft 那条不算"


def test_rank_short_repo_name_alone_is_not_enough():
    """仅 2 字符的仓库名出现在无关页面里，不应算相关。"""
    results = [SearchResult("Google 搜索", "https://google.com", "go 语言", "google.com")]
    _, relevant = search._rank(results, "someone/go")
    assert relevant == 0, '"go" 出现在 "google" 里属于子串误命中'


def test_rank_github_domain_always_relevant():
    results = [SearchResult("GitHub - x/y", "https://github.com/x/y", "d", "github.com")]
    _, relevant = search._rank(results, "x/y")
    assert relevant == 1


def test_search_repo_marks_broad_match_for_owner_collision(monkeypatch):
    """端到端回归：owner 名撞上同形词时，整条链路必须标记为宽泛匹配。"""
    monkeypatch.setattr(search, "_bing", lambda *a: [
        SearchResult("光学成像中的点扩散函数（PSF）", "https://zhuanlan.zhihu.com/p/1", "PSF", "zhuanlan.zhihu.com"),
        SearchResult("点扩散函数_百度百科", "https://baike.baidu.com/item/PSF", "PSF", "baike.baidu.com"),
        SearchResult("PSF 与去卷积", "https://blog.csdn.net/x", "PSF", "blog.csdn.net"),
    ])
    out = search.search_repo("psf/requests", "Python HTTP library")
    assert out.provider == "bing"
    assert out.degraded is True, "全是无关结果时必须标记宽泛匹配"
    assert "宽泛匹配" in out.note
