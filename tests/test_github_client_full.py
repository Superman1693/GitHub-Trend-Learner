"""GitHub 客户端（app/github_client.py）测试。

此前覆盖率仅 50%，未覆盖的正是最危险的分支：
限流等待（X-RateLimit-Reset）、5xx 退避、404 语义、以及 get_tree 的空仓库 409。
这些分支出错的表现是「静默降级」或「长时间卡死」，比抛异常更难排查。

用假 Session 驱动，不触网、不真实等待。
"""
from __future__ import annotations

import base64
import json

import pytest
import requests

from app import github_client as gh
from app.github_client import GitHubClient, GitHubError, RateLimited, RepoNotFound


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(gh.time, "sleep", lambda *_: None)


class _Resp:
    def __init__(self, status=200, payload=None, text="", headers=None):
        self.status_code = status
        self._payload = payload
        self.text = text or json.dumps(payload or {})
        self.headers = headers or {}

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class FakeSession:
    """按序返回预设响应（也可以是异常，用于模拟网络错误）。"""

    def __init__(self, responses):
        self._responses = list(responses)
        self.headers: dict[str, str] = {}
        self.calls: list[tuple[str, dict]] = []

    def get(self, url, timeout=None, **kwargs):
        self.calls.append((url, kwargs))
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _client(responses, **kw) -> GitHubClient:
    c = GitHubClient(token="t", max_retries=kw.pop("max_retries", 3), **kw)
    c.session = FakeSession(responses)
    return c


# ---------------- 404 语义 ----------------

def test_404_raises_repo_not_found():
    c = _client([_Resp(404)])
    with pytest.raises(RepoNotFound):
        c.get_repo("a/b")


def test_404_is_not_retried():
    """404 是语义性失败，重试无意义（Req2.4）。"""
    c = _client([_Resp(404)])
    with pytest.raises(RepoNotFound):
        c.get_repo("a/b")
    assert len(c.session.calls) == 1


# ---------------- 限流 ----------------

def test_rate_limit_waits_then_retries(monkeypatch):
    """403 + remaining=0 且重置时间不远时，应等待后重试（而非直接失败）。"""
    monkeypatch.setattr(gh.time, "time", lambda: 1_000_000.0)
    waited: list[float] = []
    monkeypatch.setattr(gh.time, "sleep", lambda s: waited.append(s))

    reset = int(1_000_000 + 5)
    seq = [
        _Resp(403, headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(reset)}),
        _Resp(200, {"full_name": "a/b"}),
    ]
    c = _client(seq, max_retries=3)
    assert c.get_repo("a/b")["full_name"] == "a/b"
    assert waited and waited[0] == 6.0, "应等待 reset 到期 +1 秒"
    assert len(c.session.calls) == 2


def test_rate_limit_raises_when_reset_too_far(monkeypatch):
    """重置时间超过上限时不该死等，直接抛 RateLimited。"""
    monkeypatch.setattr(gh.time, "time", lambda: 1_000_000.0)
    reset = int(1_000_000 + 3600)
    c = _client([_Resp(403, headers={"X-RateLimit-Remaining": "0",
                                     "X-RateLimit-Reset": str(reset)})],
                max_retries=3, max_rate_limit_wait=900)
    with pytest.raises(RateLimited):
        c.get_repo("a/b")
    assert len(c.session.calls) == 1


def test_429_with_remaining_zero_also_treated_as_rate_limit(monkeypatch):
    monkeypatch.setattr(gh.time, "time", lambda: 1_000_000.0)
    reset = int(1_000_000 + 3600)
    c = _client([_Resp(429, headers={"X-RateLimit-Remaining": "0",
                                     "X-RateLimit-Reset": str(reset)})], max_retries=3)
    with pytest.raises(RateLimited):
        c.get_repo("a/b")


def test_403_without_zero_remaining_is_not_rate_limit():
    """remaining>0 的 403 是权限问题，不该被当成限流等待。"""
    c = _client([_Resp(403, {"message": "forbidden"}, headers={"X-RateLimit-Remaining": "42"})])
    with pytest.raises(GitHubError) as exc:
        c.get_repo("a/b")
    assert exc.value.status == 403


# ---------------- 5xx 退避 ----------------

def test_5xx_retries_then_succeeds():
    seq = [_Resp(500), _Resp(502), _Resp(200, {"full_name": "a/b"})]
    c = _client(seq, max_retries=3)
    assert c.get_repo("a/b")["full_name"] == "a/b"
    assert len(c.session.calls) == 3


def test_5xx_exhausted_raises():
    c = _client([_Resp(503), _Resp(503), _Resp(503)], max_retries=3)
    with pytest.raises(GitHubError):
        c.get_repo("a/b")


def test_network_error_retries_then_succeeds():
    seq = [requests.RequestException("boom"), _Resp(200, {"full_name": "a/b"})]
    c = _client(seq, max_retries=2)
    assert c.get_repo("a/b")["full_name"] == "a/b"


def test_network_error_exhausted_raises():
    c = _client([requests.RequestException("x")] * 2, max_retries=2)
    with pytest.raises(requests.RequestException):
        c.get_repo("a/b")


def test_other_4xx_raises_immediately():
    """422 等确定性错误不重试。"""
    c = _client([_Resp(422, {"message": "bad"})], max_retries=3)
    with pytest.raises(GitHubError) as exc:
        c.get_repo("a/b")
    assert exc.value.status == 422
    assert len(c.session.calls) == 1


# ---------------- get_page ----------------

def test_get_page_returns_on_200():
    c = _client([_Resp(200, None, text="<html>ok</html>")])
    assert c.get_page("https://github.com/trending").text == "<html>ok</html>"


def test_get_page_retries_non_200_then_raises():
    c = _client([_Resp(500, None, text="err")] * 3, max_retries=3)
    with pytest.raises(GitHubError):
        c.get_page("https://github.com/trending")


# ---------------- 数据接口 ----------------

def test_get_tree_filters_types_and_reports_truncation():
    payload = {"truncated": True,
               "tree": [{"path": "a.py", "type": "blob"},
                        {"path": "src", "type": "tree"},
                        {"path": "sub", "type": "commit"}]}
    c = _client([_Resp(200, payload)])
    paths, truncated = c.get_tree("a/b", "main")
    assert paths == ["a.py", "src"], "只保留 blob/tree"
    assert truncated is True


def test_get_tree_409_means_empty_repo():
    """空仓库（尚无提交）GitHub 返回 409，应视为空树而非错误。"""
    c = _client([_Resp(409, {"message": "Git Repository is empty."})])
    assert c.get_tree("a/b", "main") == ([], False)


def test_get_tree_404_still_raises():
    c = _client([_Resp(404)])
    with pytest.raises(RepoNotFound):
        c.get_tree("a/b", "main")


def test_get_readme_decodes_base64():
    payload = {"content": base64.b64encode("# 标题\n正文".encode("utf-8")).decode("ascii")}
    c = _client([_Resp(200, payload)])
    assert c.get_readme("a/b") == "# 标题\n正文"


def test_get_branch_sha_returns_sha():
    c = _client([_Resp(200, {"sha": "abc123"})])
    assert c.get_branch_sha("a/b", "main") == "abc123"


def test_get_branch_sha_missing_sha_returns_empty():
    c = _client([_Resp(200, {})])
    assert c.get_branch_sha("a/b", "main") == ""


def test_search_repos_returns_items():
    c = _client([_Resp(200, {"items": [{"full_name": "a/b"}]})])
    assert c.search_repos("python")[0]["full_name"] == "a/b"


def test_search_repos_missing_items_returns_empty():
    c = _client([_Resp(200, {})])
    assert c.search_repos("python") == []


def test_token_sets_authorization_header():
    c = GitHubClient(token="secret-token")
    assert c.session.headers["Authorization"] == "Bearer secret-token"


def test_no_token_has_no_authorization_header():
    c = GitHubClient(token=None)
    assert "Authorization" not in c.session.headers


def test_get_file_url_encodes_path_but_keeps_slashes():
    """含 # 或空格的文件路径必须编码，否则 URL 会被截断。"""
    c = _client([_Resp(200, None, text="content")])
    c.get_file("a/b", "docs/my file#1.md", "main")
    url = c.session.calls[0][0]
    assert "my%20file%231.md" in url
    assert url.endswith("/contents/docs/my%20file%231.md")
