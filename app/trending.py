"""热门榜单（design.md §6.2）。

- 主方案 A：解析 https://github.com/trending 页面（语义最贴近「热门」，含今日新增 star）。
- 降级方案 B：GitHub Search API `created:>YYYY-MM-DD sort=stars`（官方接口，口径为「新建且高星」）。
- 事实前提：GitHub 没有官方 Trending API；输出必须标注数据来源（Req1.6）。
"""
from __future__ import annotations

import html
import re
from datetime import date, timedelta

from . import log
from .github_client import GitHubClient

TRENDING_URL = "https://github.com/trending"

# 聚合入口（v1.8）：GitHub 的 `?since=daily` 单入口只返回约 9 个仓库，
# 单一入口会让候选池过小。改为多入口聚合去重，池子可扩到 80+。
# 顺序即优先级：日榜最贴近「近期热门」，其次是周/月榜、中文榜与各语言榜。
AGGREGATE_SOURCES: tuple[str, ...] = (
    "/trending?since=daily",
    "/trending?since=weekly",
    "/trending?since=monthly",
    "/trending?spoken_language_code=zh&since=daily",
    "/trending?spoken_language_code=zh&since=weekly",
    "/trending/python?since=daily",
    "/trending/javascript?since=daily",
    "/trending/typescript?since=daily",
    "/trending/go?since=daily",
    "/trending/rust?since=daily",
    "/trending/java?since=daily",
    "/trending/c++?since=daily",
    "/trending/c?since=daily",
    "/trending/c%23?since=daily",
    "/trending/php?since=daily",
    "/trending/ruby?since=daily",
    "/trending/swift?since=daily",
    "/trending/kotlin?since=daily",
    "/trending/shell?since=daily",
    "/trending/vue?since=daily",
    "/trending/dart?since=daily",
    "/trending/jupyter-notebook?since=daily",
    "/trending/html?since=daily",
    "/trending/css?since=daily",
)

# trending 页面中的仓库行：<h2 ...><a href="/owner/repo">…</a></h2>；今日 star 含「N stars today」
_ROW = re.compile(r'<h2[^>]*>\s*<a[^>]+href="/([\w.-]+/[\w.-]+)"', re.S)
_STARS_TODAY = re.compile(r"([\d,]+)\s*stars?\s*today", re.I)
# v1.7：补齐元信息提取，否则候选池的规则打标与筛选全部失效（语言/star/描述为空）
_DESCRIPTION = re.compile(r'<p[^>]*class="[^"]*col-9[^"]*"[^>]*>(.*?)</p>', re.S)
_LANGUAGE = re.compile(r'itemprop="programmingLanguage"[^>]*>(.*?)</span>', re.S)
_STARS_TOTAL = re.compile(r'href="/[^"]+/stargazers"[^>]*>.*?([\d,]+)\s*</a>', re.S)
_FORKS = re.compile(r'href="/[^"]+/forks"[^>]*>.*?([\d,]+)\s*</a>', re.S)
_TAGS = re.compile(r"<[^>]+>")

# 页面导航区也可能出现 /features/xxx、/topics/xxx 形式的两段链接，需排除
_NON_REPO_PREFIXES = {
    "features", "topics", "collections", "trending", "about", "pricing",
    "security", "marketplace", "explore", "settings", "orgs", "apps",
    "customer-stories", "readme", "enterprise", "team", "sponsors",
    "login", "join", "site", "events", "education",
}


def _num(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        return int(raw.replace(",", "").strip())
    except ValueError:
        return None


def _text(raw: str | None) -> str:
    return html.unescape(_TAGS.sub("", raw or "")).strip()


def parse_trending_html(html_text: str) -> list[dict]:
    """解析 trending 页面 HTML（纯函数，离线可测）。

    返回 [{full_name, html_url, description, language, stars, forks, stars_today}]。
    v1.7 起补齐元信息：候选池的规则打标与多条件筛选依赖这些字段，
    早期只取仓库名与今日 star，导致打标全部退化为 unknown。
    """
    items: list[dict] = []
    seen: set[str] = set()
    for chunk in html_text.split("<article")[1:]:
        m = _ROW.search(chunk)
        if not m:
            continue
        name = m.group(1).rstrip(".")
        if name in seen or name.count("/") != 1:
            continue
        if name.split("/", 1)[0] in _NON_REPO_PREFIXES:
            continue
        seen.add(name)

        desc = _DESCRIPTION.search(chunk)
        lang = _LANGUAGE.search(chunk)
        stars = _STARS_TOTAL.search(chunk)
        forks = _FORKS.search(chunk)
        today = _STARS_TODAY.search(chunk)

        items.append({
            "full_name": name,
            "html_url": f"https://github.com/{name}",
            "description": _text(desc.group(1)) if desc else "",
            "language": _text(lang.group(1)) if lang else None,
            "stars": _num(stars.group(1)) if stars else None,
            "forks": _num(forks.group(1)) if forks else None,
            "stars_today": _num(today.group(1)) if today else None,
            "topics": [],
        })
    return items


def enrich_repo_metadata(
    client: GitHubClient,
    repos: list[dict],
    *,
    max_workers: int = 5,
    limit: int | None = None,
) -> int:
    """补齐 trending 页面缺失的元信息（topics / 描述 / 语言 / star / fork）。

    trending 页面**不包含 topics**，而规则打标高度依赖 topics，
    导致大量候选退化为「待进一步了解」。这里逐个补一次 `/repos/{full_name}`
    （1 次调用/仓库，并发执行）；单个仓库失败不影响其他仓库。

    返回成功补齐的仓库数。
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    targets = [r for r in repos if not r.get("topics")]
    if limit is not None:
        targets = targets[:limit]
    if not targets:
        return 0

    def _fetch(repo: dict) -> tuple[str, dict | None]:
        try:
            data = client.get_repo(repo["full_name"])
        except Exception:  # noqa: BLE001 - 补齐失败保持原样
            return repo["full_name"], None
        return repo["full_name"], data

    filled = 0
    by_name = {r["full_name"]: r for r in repos}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(_fetch, r) for r in targets]
        for fut in as_completed(futures):
            name, data = fut.result()
            if not data:
                continue
            repo = by_name.get(name)
            if repo is None:
                continue
            repo["topics"] = data.get("topics") or []
            repo["description"] = (data.get("description") or repo.get("description") or "").strip()
            repo["language"] = data.get("language") or repo.get("language")
            repo["stars"] = data.get("stargazers_count") or repo.get("stars")
            repo["forks"] = data.get("forks_count") or repo.get("forks")
            repo["license"] = (data.get("license") or {}).get("spdx_id") if data.get("license") else None
            repo["homepage"] = data.get("homepage")
            filled += 1
    return filled


def _merge_into(pool: dict[str, dict], items: list[dict], label: str) -> None:
    """把一次抓取的结果并入池子；同一仓库保留今日 star 更高的记录并累计来源。"""
    for item in items:
        name = item["full_name"]
        existing = pool.get(name)
        if existing is None:
            item = dict(item)
            item["sources"] = [label]
            pool[name] = item
            continue
        if label not in existing["sources"]:
            existing["sources"].append(label)
        cur, new = existing.get("stars_today") or 0, item.get("stars_today") or 0
        if new > cur:
            existing["stars_today"] = new
        # 描述/语言缺失时用新记录补上
        for field in ("description", "language", "html_url", "topics"):
            if not existing.get(field) and item.get(field):
                existing[field] = item[field]


def _rank_repos(items: list[dict]) -> list[dict]:
    """今日 star 降序，其次总 star 降序，保证榜单最有代表性的排前面。"""
    return sorted(
        items,
        key=lambda r: (r.get("stars_today") or 0, r.get("stars") or 0),
        reverse=True,
    )


def fetch_trending(client: GitHubClient, top_n: int) -> tuple[list[dict], str]:
    """获取热门仓库列表，返回 (repos, source)；source ∈ trending_page | search_api。

    **多入口聚合**：依次抓取 AGGREGATE_SOURCES，去重后按热度排序；
    凑够 top_n 或入口用尽即停止。主方案整体失败才降级到 Search API（Req1.1、Req1.6）。
    """
    pool: dict[str, dict] = {}
    try:
        for path in AGGREGATE_SOURCES:
            label = path.replace("/trending", "").lstrip("?") or "daily"
            try:
                resp = client.get_page(f"https://github.com{path}")
            except Exception:  # noqa: BLE001 - 单个入口失败继续下一个
                continue
            items = parse_trending_html(resp.text)
            if items:
                _merge_into(pool, items, label)
            if len(pool) >= top_n:
                break
        if pool:
            repos = _rank_repos(list(pool.values()))[:top_n]
            return repos, "trending_page"
        log.console("  [降级] trending 页面解析结果为空，改用 Search API")
    except Exception as exc:  # 网络/SSL 失败等，一律降级（Req1.4）
        log.console(f"  [降级] trending 页面不可达（{exc}），改用 Search API")

    # 降级方案 B：Search API（有独立的限流配额，必须单独兜异常，
    # 否则限流异常会冒泡出 fetch_trending，导致整日任务直接归零 —— v1.8 修复）
    try:
        since = (date.today() - timedelta(days=7)).isoformat()
        items = client.search_repos(f"created:>{since} stars:>50", per_page=max(top_n, 30))
    except Exception as exc:  # noqa: BLE001
        log.console(f"  [降级] Search API 亦不可用（{type(exc).__name__}: {exc}）")
        return [], "search_api"
    repos = [
        {
            "full_name": item["full_name"],
            "html_url": item.get("html_url"),
            "stars_today": None,
            "stars": item.get("stargazers_count"),
            "forks": item.get("forks_count"),
            "description": item.get("description"),
            "language": item.get("language"),
            "topics": item.get("topics") or [],
        }
        for item in items[:top_n]
    ]
    return repos, "search_api"
