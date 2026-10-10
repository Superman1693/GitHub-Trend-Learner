"""GitHub REST API v3 直连（design.md §6.1 v1.4 实现口径、§9 异常策略）。只读语义。

- 限流：403/429 且 X-RateLimit-Remaining=0 时按 X-RateLimit-Reset 等待后重试（global.md §7.2，禁止无脑重试）。
- 404：无法区分「不存在」与「私有」，统一 RepoNotFound（Req2.4、约束 C3）。
- 网络/5xx：指数退避，总重试 ≤3。
"""
from __future__ import annotations

import base64
import time
from urllib.parse import quote

import requests

from . import log

API_BASE = "https://api.github.com"


class GitHubError(Exception):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class RateLimited(GitHubError):
    """限流且重置时间过长 / 重试耗尽。"""


class RepoNotFound(GitHubError):
    """404：链接无效，或该仓库为私有/已删除（未授权状态下无法区分）。"""


class GitHubClient:
    def __init__(self, token: str | None = None, max_retries: int = 3,
                 timeout: int = 30, max_rate_limit_wait: int = 900) -> None:
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "GitHub-Trend-Learner/1.0",
        })
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"
        self.max_retries = max_retries
        self.timeout = timeout
        self.max_rate_limit_wait = max_rate_limit_wait

    # ---- 底层请求 ----

    def _get(self, url: str, **kwargs) -> requests.Response:
        last_err: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(url, timeout=self.timeout, **kwargs)
            except requests.RequestException as exc:
                last_err = exc
                time.sleep(min(2 ** attempt, 30))
                continue
            if resp.status_code == 404:
                raise RepoNotFound(url)
            if resp.status_code in (403, 429) and resp.headers.get("X-RateLimit-Remaining") == "0":
                reset = int(resp.headers.get("X-RateLimit-Reset") or 0)
                wait = max(reset - time.time(), 0) + 1
                if reset and wait <= self.max_rate_limit_wait and attempt < self.max_retries:
                    log.console(f"  [限流] 等待 {int(wait)}s 后重试（X-RateLimit-Reset）")
                    time.sleep(wait)
                    continue
                raise RateLimited(f"GitHub 限流，重置需等待 {int(wait)}s")
            if resp.status_code >= 500:
                last_err = GitHubError(f"HTTP {resp.status_code}", status=resp.status_code)
                time.sleep(min(2 ** attempt, 30))
                continue
            if resp.status_code >= 400:
                raise GitHubError(f"HTTP {resp.status_code}: {resp.text[:200]}",
                                  status=resp.status_code)
            return resp
        raise last_err or GitHubError("重试耗尽")

    def get_page(self, url: str) -> requests.Response:
        """普通网页 GET（trending 页面解析用，design.md §6.2 主方案）。"""
        last_err: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(url, timeout=self.timeout,
                                        headers={"Accept": "text/html"})
                if resp.status_code == 200:
                    return resp
                last_err = GitHubError(f"HTTP {resp.status_code}")
            except requests.RequestException as exc:
                last_err = exc
            time.sleep(min(2 ** attempt, 30))
        raise last_err or GitHubError("重试耗尽")

    # ---- 数据接口（design.md §6.1 能力对照表） ----

    def get_repo(self, full_name: str) -> dict:
        """仓库元信息（star、language、License、default_branch、head_sha）。"""
        return self._get(f"{API_BASE}/repos/{full_name}").json()

    def get_readme(self, full_name: str) -> str:
        """README 全文（base64 解码）。

        **无 README 是常见情况，不是错误**：GitHub 对没有 README 的仓库返回 404，
        若直接冒泡 `RepoNotFound`，上层会把「公开仓库但没写 README」误报成
        「链接无效或私有/已删除」（v1.8 修复）。这里返回空串，由上层记入降级原因。
        """
        try:
            data = self._get(f"{API_BASE}/repos/{full_name}/readme").json()
        except RepoNotFound:
            return ""
        return base64.b64decode(data.get("content", "")).decode("utf-8", errors="replace")

    def get_tree(self, full_name: str, branch: str) -> tuple[list[str], bool]:
        """目录树（recursive）；返回 (路径列表, 是否被截断)。

        空仓库（尚无提交）GitHub 返回 409，视为空树而非错误。
        """
        try:
            data = self._get(f"{API_BASE}/repos/{full_name}/git/trees/{branch}?recursive=1").json()
        except GitHubError as exc:
            if exc.status == 409:
                return [], False
            raise
        paths = [item["path"] for item in data.get("tree", [])
                 if item.get("type") in ("blob", "tree")]
        return paths, bool(data.get("truncated"))

    def get_file(self, full_name: str, path: str, ref: str) -> str:
        """读取单个文件内容（核心文件筛选后取内容）。路径做 URL 编码防止 # ? 等字符断链。"""
        resp = self._get(f"{API_BASE}/repos/{full_name}/contents/{quote(path, safe='/')}",
                         params={"ref": ref}, headers={"Accept": "application/vnd.github.raw"})
        return resp.text

    def get_branch_sha(self, full_name: str, ref: str) -> str:
        """分支头提交 sha（缓存键用，design.md §8.2）。"""
        return self._get(f"{API_BASE}/repos/{full_name}/commits/{ref}").json().get("sha", "")

    def search_repos(self, query: str, per_page: int = 30) -> list[dict]:
        """仓库搜索（Search API，design.md §6.2 降级方案 B）。"""
        resp = self._get(f"{API_BASE}/search/repositories",
                         params={"q": query, "sort": "stars", "order": "desc",
                                 "per_page": per_page})
        return resp.json().get("items", [])
