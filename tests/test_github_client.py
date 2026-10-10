"""GitHubClient 特殊场景：空仓库 409、文件路径 URL 编码。"""
from app.github_client import GitHubClient, GitHubError


def test_get_tree_empty_repo_returns_empty(monkeypatch):
    """空仓库（无提交）tree 接口返回 409，应视为空树而非错误（第三轮缺陷 #4 回归）。"""
    c = GitHubClient()

    def fake_get(url, **kw):
        raise GitHubError("HTTP 409", status=409)

    monkeypatch.setattr(c, "_get", fake_get)
    assert c.get_tree("a/b", "main") == ([], False)


def test_get_tree_other_errors_propagate(monkeypatch):
    c = GitHubClient()

    def fake_get(url, **kw):
        raise GitHubError("HTTP 500", status=500)

    monkeypatch.setattr(c, "_get", fake_get)
    try:
        c.get_tree("a/b", "main")
        assert False, "应抛出异常"
    except GitHubError as exc:
        assert exc.status == 500


def test_get_file_quotes_special_chars(monkeypatch):
    """路径含 # 等字符时须 URL 编码，避免请求断链（第三轮缺陷 #5 回归）。"""
    c = GitHubClient()
    seen = {}

    def fake_get(url, **kw):
        seen["url"] = url
        class R:
            text = "content"
        return R()

    monkeypatch.setattr(c, "_get", fake_get)
    c.get_file("a/b", "docs/FAQ#1.md", "main")
    assert "docs/FAQ%231.md" in seen["url"]
    assert "docs/FAQ#1.md" not in seen["url"]
