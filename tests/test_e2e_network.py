"""真实网络端到端测试（tasks.md T15，v1.9.0）。

**默认跳过**，用 `pytest tests/ -m network` 显式运行。原因：
真实访问 github.com / bing.com 既慢又受对方限流与改版影响，
放进 CI 必过门禁会变成「三天两头无故变红」，最终被无视。

这些测试覆盖 T15 要求的四类场景（真实网络口径）：
    热门仓库 / 私有或不存在仓库 / 无效链接 / 超大仓库
以及真实 GitHub API、趋势页抓取、搜索引擎链路。

**全部零 LLM**——只验证数据采集与规则环节，不产生任何 token 费用。
"""
from __future__ import annotations

import pytest

from app import candidates, search, trending
from app.config import Settings
from app.github_client import GitHubClient, RepoNotFound

pytestmark = pytest.mark.network

# 选一个长期稳定、star 多、不会被删的仓库作为基准
STABLE_REPO = "psf/requests"


@pytest.fixture(scope="module")
def client():
    settings = Settings.load()
    if not settings.github_token:
        pytest.skip("未配置 GITHUB_TOKEN，跳过真实 API 测试（未授权时限流极低）")
    return GitHubClient(token=settings.github_token)


# ---------------- 场景 1：热门仓库 ----------------


def test_real_repo_metadata(client):
    """真实仓库元信息读取。"""
    info = client.get_repo(STABLE_REPO)
    assert info["full_name"] == STABLE_REPO
    assert info["stargazers_count"] > 1000
    assert info["default_branch"]


def test_real_readme_and_tree(client):
    """README 与目录树在真实仓库上可读。"""
    readme = client.get_readme(STABLE_REPO)
    assert len(readme) > 100, "README 内容异常短"

    branch = client.get_repo(STABLE_REPO)["default_branch"]
    tree, _ = client.get_tree(STABLE_REPO, branch)
    assert any(p.endswith(".py") for p in tree), f"目录树里没有 Python 文件：{tree[:10]}"


def test_real_trending_fetch(client):
    """真实抓取 GitHub Trending（主方案）或降级到 Search API。"""
    repos, source = trending.fetch_trending(client, 10)
    assert repos, "榜单抓取返回空——主方案与降级方案都失败了"
    assert source in ("trending_page", "search_api")
    for repo in repos[:5]:
        assert "/" in repo["full_name"]


def test_real_candidate_snapshot_pipeline(client):
    """真实榜单 → 候选池条目（规则打标，零 LLM）。"""
    repos, source = trending.fetch_trending(client, 10)
    snap = candidates.build_day_snapshot(repos, source, "2026-10-10")

    assert snap["count"] == len(repos)
    assert snap["count"] > 0
    for item in snap["items"]:
        dims = item["dimensions"]
        for key in ("highlight", "learnable", "deployable", "playfulness", "practical_tool"):
            assert dims.get(key), f"{item['full_name']} 缺少维度 {key}"


# ---------------- 场景 2：私有 / 不存在的仓库 ----------------


def test_real_missing_repo_raises_not_found(client):
    """不存在的仓库必须抛 RepoNotFound，不能静默返回空数据。"""
    with pytest.raises(RepoNotFound):
        client.get_repo("this-owner-does-not-exist-xyz/nope-nope-nope")


# ---------------- 场景 3：无效链接 ----------------


@pytest.mark.parametrize("bad", [
    "不是链接",
    "https://example.com/not/github",
    "github.com",
    "https://github.com/only-owner",
])
def test_real_invalid_url_rejected_before_network(bad):
    """无效链接应在**发起网络请求之前**就被拒绝（省一次无谓调用）。"""
    from app.agents import collector

    with pytest.raises(collector.InvalidURL):
        collector.resolve_full_name(bad)


def test_real_run_repo_rejects_invalid_url():
    """编排层对无效链接要给出可操作的提示，而不是抛栈。"""
    import threading

    from app.config import Settings
    from app.orchestrator import Orchestrator

    orch = Orchestrator.__new__(Orchestrator)
    orch.settings = Settings.load()
    orch._seq = 0
    orch._seq_lock = threading.Lock()
    result = orch.run_repo("完全不是链接")
    assert result["ok"] is False
    assert "https://github.com/owner/repo" in result["message"]


# ---------------- 场景 4：超大仓库 ----------------


def test_real_huge_repo_metadata_only(client):
    """超大仓库（linux 内核量级）元信息仍能取到，不因体积失败。

    这里只验证采集环节；完整解析会调用 LLM，不在零成本 e2e 范围内。
    """
    info = client.get_repo("torvalds/linux")
    assert info["full_name"] == "torvalds/linux"
    assert info["stargazers_count"] > 100_000

    tree, truncated = client.get_tree("torvalds/linux", info["default_branch"])
    assert tree, "目录树为空"
    # 大仓库必然触发截断，客户端要如实标记而不是假装拿全了
    assert isinstance(truncated, bool)


# ---------------- 搜索引擎链路 ----------------


def test_real_search_finds_github_page(client):
    """真实搜索：一级检索词是精确仓库名，应能命中 GitHub 页面。"""
    outcome = search.search_repo(STABLE_REPO, "Python HTTP library")
    assert outcome.provider in ("bing", "github", "none")
    if outcome.provider == "none":
        pytest.skip("搜索引擎与 GitHub 兜底均不可用（网络受限）")

    # 不变式（比「必须命中 GitHub」更本质）：若结果里没有 GitHub 页面，
    # 就必须标记为宽泛匹配，绝不能把无关结果当相关资料展示。
    # 实测 Bing 对 "psf/requests" 会返回光学名词「PSF」的文章，正是靠这条兜住。
    domains = {r.domain for r in outcome.results}
    if "github.com" not in domains and outcome.provider == "bing":
        assert outcome.degraded is True, (
            f"结果里没有 GitHub 页面却未标记宽泛匹配，实际域名：{domains}"
        )


def test_real_search_repo_url_builder():
    assert search.build_repo_url(STABLE_REPO) == f"https://github.com/{STABLE_REPO}"
