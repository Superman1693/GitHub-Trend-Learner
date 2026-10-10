"""搜索引擎接入（design.md §16.8）。

**阶段一专用**：只做检索与结果聚合，**不做任何生成式总结**，不调用 LLM。
用户看到的每一行都来自搜索引擎的原始结果，避免误以为是 AI 结论。

提供方：
    bing    —— 主提供方，解析 `li.b_algo` 结构（实测可达且结构稳定）
    github  —— 兜底，主提供方失败时改用 GitHub 仓库搜索
"""
from __future__ import annotations

import base64
import html
import re
import time
from dataclasses import asdict, dataclass, field
from urllib.parse import quote, urlparse

import requests

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_BING_BLOCK = re.compile(r'<li class="b_algo".*?</li>', re.S)
_BING_LINK = re.compile(r'<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)
_BING_SNIP = re.compile(r"<p[^>]*>(.*?)</p>", re.S)
_TAGS = re.compile(r"<[^>]+>")
_BING_REDIRECT = re.compile(r"[?&]u=a1([^&]+)")


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    domain: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SearchOutcome:
    query: str
    provider: str
    results: list[SearchResult] = field(default_factory=list)
    took_ms: int = 0
    degraded: bool = False
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "provider": self.provider,
            "results": [r.to_dict() for r in self.results],
            "took_ms": self.took_ms,
            "degraded": self.degraded,
            "note": self.note,
            "disclaimer": "以下为搜索引擎返回的原始结果，非 AI 生成内容。",
        }


def _clean(text: str) -> str:
    return html.unescape(_TAGS.sub("", text or "")).strip()


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _unwrap_bing(url: str) -> str:
    """Bing 部分结果走跳转链（`/ck/a?u=a1<base64url>`），还原真实地址。"""
    m = _BING_REDIRECT.search(url)
    if not m:
        return url
    raw = m.group(1)
    padding = "=" * (-len(raw) % 4)
    try:
        decoded = base64.urlsafe_b64decode(raw + padding).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 - 解不出来就保留原链接
        return url
    return decoded if decoded.startswith("http") else url


def build_query(full_name: str, description: str | None = None) -> str:
    """构造检索词：**优先精确仓库名**，描述仅作兜底。

    早期把描述关键词直接拼进检索词，对冷门仓库会把结果带偏
    （实测 `morluto/rea` + "Reverse engineer anything" 返回了一堆名人名言页）。
    现在改为「精确名 → 名+github → 名+描述词」三级递进。
    """
    return f'"{full_name}"'


def _desc_words(description: str | None) -> str:
    if not description:
        return ""
    words = re.findall(r"[A-Za-z][A-Za-z0-9+.#-]{2,}", description)[:3]
    return " ".join(words)


def _rank(results: list[SearchResult], full_name: str) -> tuple[list[SearchResult], int]:
    """按相关性排序：仓库主页优先，其次标题/摘要命中仓库名。

    返回 (排序后的结果, 相关结果数)。相关数为 0 时调用方应标注「宽泛匹配」，
    避免用户把无关结果误当成该仓库的资料。
    """
    owner, _, repo = full_name.partition("/")
    repo_l, owner_l = repo.lower(), owner.lower()

    def score(r: SearchResult) -> int:
        s = 0
        if "github.com" in r.domain:
            s += 3
        blob = f"{r.title} {r.snippet}".lower()
        if repo_l and len(repo_l) >= 2 and repo_l in blob:
            s += 2
        # owner 可能是单字符（如 a/b），过短会命中任意单词，故要求长度 ≥3
        if owner_l and len(owner_l) >= 3 and owner_l in blob:
            s += 1
        return s

    ranked = sorted(results, key=score, reverse=True)
    relevant = [r for r in ranked if score(r) > 0]
    return (relevant if len(relevant) >= 3 else ranked), len(relevant)


def _bing(query: str, limit: int, timeout: int) -> list[SearchResult]:
    resp = requests.get(
        "https://www.bing.com/search",
        params={"q": query, "count": max(limit, 10)},
        headers=UA,
        timeout=timeout,
    )
    resp.raise_for_status()
    out: list[SearchResult] = []
    for block in _BING_BLOCK.findall(resp.text):
        m = _BING_LINK.search(block)
        if not m:
            continue
        url = _unwrap_bing(html.unescape(m.group(1)))
        title = _clean(m.group(2))
        sn = _BING_SNIP.search(block)
        snippet = _clean(sn.group(1)) if sn else ""
        if not title or not url.startswith("http"):
            continue
        out.append(SearchResult(title=title, url=url, snippet=snippet, domain=_domain(url)))
        if len(out) >= limit:
            break
    return out


def _github(full_name: str, limit: int, timeout: int) -> list[SearchResult]:
    """兜底：用 GitHub 仓库搜索，把命中项转成结果条目。"""
    from .config import Settings

    token = Settings.load().github_token
    headers = dict(UA)
    headers["Accept"] = "application/vnd.github+json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    resp = requests.get(
        "https://api.github.com/search/repositories",
        params={"q": full_name, "per_page": limit},
        headers=headers,
        timeout=timeout,
    )
    resp.raise_for_status()
    items = (resp.json() or {}).get("items") or []
    out: list[SearchResult] = []
    for it in items[:limit]:
        out.append(
            SearchResult(
                title=it.get("full_name") or "",
                url=it.get("html_url") or "",
                snippet=(it.get("description") or "").strip(),
                domain="github.com",
            )
        )
    return out


def search_repo(
    full_name: str,
    description: str | None = None,
    *,
    limit: int = 8,
    timeout: int = 8,
) -> SearchOutcome:
    """阶段一入口：检索仓库相关外部资料。**不调用 LLM。**

    三级检索策略（前一级有结果就不继续），命中后做相关性排序；
    主提供方整体失败时降级到 GitHub 搜索，并在结果中标注 provider 与 degraded。
    """
    started = time.perf_counter()
    desc = _desc_words(description)
    attempts = [f'"{full_name}"', f"{full_name} github"]
    if desc:
        attempts.append(f"{full_name} {desc}")

    note = ""
    for query in attempts:
        try:
            results = _bing(query, limit * 2, timeout)
        except Exception as exc:  # noqa: BLE001
            note = f"主搜索提供方不可用（{type(exc).__name__}），已改用 GitHub 搜索。"
            break
        if results:
            ranked, relevant = _rank(results, full_name)
            return SearchOutcome(
                query=query, provider="bing", results=ranked[:limit],
                took_ms=int((time.perf_counter() - started) * 1000),
                degraded=relevant == 0,
                note=("未找到与该仓库直接相关的结果，以下为搜索引擎的宽泛匹配，请谨慎参考。"
                      if relevant == 0 else ""),
            )
    else:
        note = "主搜索提供方未返回结果，已改用 GitHub 搜索。"

    try:
        results = _github(full_name, limit, timeout)
        return SearchOutcome(
            query=full_name, provider="github", results=results,
            took_ms=int((time.perf_counter() - started) * 1000),
            degraded=True, note=note,
        )
    except Exception as exc:  # noqa: BLE001
        return SearchOutcome(
            query=full_name, provider="none", results=[],
            took_ms=int((time.perf_counter() - started) * 1000),
            degraded=True,
            note=f"搜索引擎均不可用：{type(exc).__name__}。可稍后重试或直接打开仓库查看。",
        )


def search_query(raw: str, *, limit: int = 8, timeout: int = 8) -> SearchOutcome:
    """按自定义关键词检索（供「换一批关键词」使用）。"""
    started = time.perf_counter()
    try:
        results = _bing(raw, limit, timeout)
        return SearchOutcome(query=raw, provider="bing", results=results,
                             took_ms=int((time.perf_counter() - started) * 1000))
    except Exception as exc:  # noqa: BLE001
        return SearchOutcome(query=raw, provider="none", results=[],
                             took_ms=int((time.perf_counter() - started) * 1000),
                             degraded=True, note=f"检索失败：{type(exc).__name__}")


def build_repo_url(full_name: str) -> str:
    return f"https://github.com/{full_name}"


def quote_query(text: str) -> str:
    return quote(text, safe="")
