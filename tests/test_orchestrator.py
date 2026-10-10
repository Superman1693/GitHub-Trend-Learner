"""编排器（app/orchestrator.py）测试。

该模块此前覆盖率仅 28%，是全项目最大的测试缺口。它是流程中枢：
路由分类、缓存命中短路、降级四件套、子阶段重试、以及
「仅门禁通过才写缓存」这条 v1.5 修过的关键规则——写错会导致
质量不达标的文档被永久复用、再也不重试。

所有外部依赖（GitHub / LLM / 三个 Agent）均用假实现替换，不触网。
"""
from __future__ import annotations

import threading

import pytest

from app import orchestrator as orch_mod
from app.config import MAX_AUTO_PARSE, Settings
from app.contracts import MODULES_ORDER, FinalDoc, RepoMeta, TaskEnvelope
from app.orchestrator import HELP_TEXT, Orchestrator

# ---------------- 假实现 ----------------

@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """子阶段重试带指数退避，测试里不应真实等待。"""
    monkeypatch.setattr(orch_mod.time, "sleep", lambda *_: None)


class FakeClient:
    def __init__(self, repo_info=None, sha="a" * 40, error=None):
        self._repo = repo_info if repo_info is not None else {"full_name": "a/b",
                                                              "html_url": "https://github.com/a/b",
                                                              "default_branch": "main"}
        self._sha = sha
        self._error = error

    def get_repo(self, full_name):
        if self._error:
            raise self._error
        return self._repo

    def get_branch_sha(self, full_name, ref):
        if self._error:
            raise self._error
        return self._sha


class FakeCache:
    def __init__(self, hit=None, trending=None):
        self._hit = hit
        self._trending = trending
        self.stored: list[tuple] = []
        self.trending_put: list[tuple] = []

    def get(self, full_name, head_sha):
        return self._hit

    def put(self, full_name, head_sha, finaldoc, generated_at, meta=None):
        self.stored.append((full_name, head_sha, finaldoc))

    def get_trending(self, day):
        return self._trending

    def put_trending(self, day, repos, source):
        self.trending_put.append((repos, source))


class FakeLLM:
    last_usage_total = 10

    def chat(self, *a, **k):
        return "{}"


def _meta() -> RepoMeta:
    return RepoMeta(full_name="a/b", html_url="https://github.com/a/b", description="d",
                    stars=1, forks=0, language="Python", license="MIT", topics=[],
                    default_branch="main", head_sha="a" * 40, fetched_at="2026-10-10 10:00",
                    source="search_api", readme="", tree=[], core_files=[])


def _draft():
    from app.contracts import DraftDoc

    return DraftDoc(project_type="tool",
                    modules={k: f"{k} 正文" for k, _ in MODULES_ORDER})


def _plan():
    from app.contracts import DeployPlan

    return DeployPlan(env_requirements=[], steps={"windows": ["a"], "macos": ["b"], "linux": ["c"]},
                      one_click_script="echo hi", static_check={"result": "pass"},
                      risks=[], m5_markdown="M5")


def _final(gate: str = "pass") -> FinalDoc:
    modules = {k: f"{k} 正文" for k, _ in MODULES_ORDER}
    return FinalDoc(task_id="", repo_full_name="a/b", generated_at="now", modules=modules,
                    gate_result=gate, rejected_items=[], glossary=[])


def _orch(monkeypatch, *, cache_hit=None, client=None, llm=FakeLLM(),
          analyst_ok=True, deploy_ok=True, gate="pass") -> Orchestrator:
    """构造一个绕过 __init__ 的 Orchestrator，外部依赖全部替换为假实现。"""
    orch = Orchestrator.__new__(Orchestrator)
    orch.settings = Settings.load()
    orch.client = client or FakeClient()
    orch.cache = FakeCache(cache_hit)
    orch.llm = llm
    orch._seq = 0
    orch._seq_lock = threading.Lock()

    def fake_collect(_client, repo_info, source="search_api", head_sha=None):
        return _meta()

    monkeypatch.setattr(orch_mod.collector, "collect_from_info", fake_collect)

    if analyst_ok:
        monkeypatch.setattr(orch_mod.analyst, "run", lambda _llm, _meta: _draft())
    else:
        def boom(*_a, **_k):
            raise RuntimeError("analyst failed")

        monkeypatch.setattr(orch_mod.analyst, "run", boom)

    monkeypatch.setattr(orch_mod.deploy, "run",
                        lambda _llm, _m, _d: (_plan(), "M5") if deploy_ok
                        else (_ for _ in ()).throw(RuntimeError("deploy failed")))
    monkeypatch.setattr(orch_mod.tutor, "run",
                        lambda _llm, _m, _d, _p, _m5, max_returns=2: _final(gate))
    return orch


# ---------------- 路由分类 ----------------

def _bare() -> Orchestrator:
    """只装 `__init__` 里那点无副作用的状态，供纯逻辑方法测试用。"""
    orch = Orchestrator.__new__(Orchestrator)
    orch.settings = Settings.load()
    orch._seq = 0
    orch._seq_lock = threading.Lock()
    return orch


@pytest.mark.parametrize("text,expected", [
    ("daily", "daily_trend"),
    ("每日", "daily_trend"),
    ("今日热门", "daily_trend"),
    ("cron", "daily_trend"),
    ("https://github.com/owner/repo", "custom_repo"),
    ("http://www.github.com/owner/repo", "custom_repo"),
    ("owner/repo", "custom_repo"),
    ("这是一段随便的话", "unknown"),
    ("", "unknown"),
])
def test_route_classification(text, expected):
    assert _bare()._route(text)[0] == expected


def test_help_text_lists_supported_inputs():
    assert "GitHub 仓库链接" in HELP_TEXT and "daily" in HELP_TEXT


def test_next_task_id_is_unique_and_prefixed():
    orch = _bare()
    ids = [orch._next_task_id("daily") for _ in range(20)]
    assert len(set(ids)) == 20
    assert all(i.startswith("daily-") for i in ids)


def test_degrade_message_has_four_parts():
    msg = _bare()._degrade_message("某环节", "某原因", "已交付X", "下一步Y")
    for part in ("失败部分", "失败原因", "已交付部分", "建议下一步"):
        assert part in msg


# ---------------- _pipeline_repo ----------------

def _env(mode="custom_repo", name="a/b") -> TaskEnvelope:
    return TaskEnvelope(task_id="t1", trace_id="t1", mode=mode, repo_full_name=name)


def test_cache_hit_short_circuits_without_collecting(monkeypatch):
    """命中缓存时不应再采集（design.md §8.2）。"""
    called = []
    monkeypatch.setattr(orch_mod.collector, "collect_from_info",
                        lambda *a, **k: called.append(1) or _meta())
    cached_doc = _final().to_dict()
    orch = _orch(monkeypatch, cache_hit={"finaldoc": cached_doc, "meta": {}})

    result = orch._pipeline_repo(_env(), source="search_api")

    assert result["ok"] is True and result["cached"] is True
    assert called == [], "命中缓存后不应再调用采集"


def test_repo_not_found_reports_link_error(monkeypatch):
    from app.github_client import RepoNotFound

    orch = _orch(monkeypatch, client=FakeClient(error=RepoNotFound("x")))
    result = orch._pipeline_repo(_env(), source="search_api")

    assert result["ok"] is False
    assert "链接无效" in result["error"]


def test_missing_llm_reports_config_error(monkeypatch):
    orch = _orch(monkeypatch, llm=None)
    result = orch._pipeline_repo(_env(), source="search_api")

    assert result["ok"] is False
    assert "LLM" in result["error"]


def test_gate_pass_stores_cache(monkeypatch):
    orch = _orch(monkeypatch, gate="pass")
    result = orch._pipeline_repo(_env(), source="search_api")

    assert result["ok"] is True
    assert len(orch.cache.stored) == 1, "门禁通过必须写缓存"
    assert result["finaldoc"]["modules"]["_project_type"] == "tool"


def test_gate_degraded_does_not_store_cache(monkeypatch):
    """v1.5 回归：降级交付的文档绝不能写缓存，否则 head_sha 不变会永久复用。"""
    orch = _orch(monkeypatch, gate="degraded")
    result = orch._pipeline_repo(_env(), source="search_api")

    assert result["ok"] is True
    assert result["finaldoc"]["gate_result"] == "degraded"
    assert orch.cache.stored == [], "降级结果不得写缓存"


def test_analyst_failure_returns_error(monkeypatch):
    orch = _orch(monkeypatch, analyst_ok=False)
    result = orch._pipeline_repo(_env(), source="search_api")

    assert result["ok"] is False
    assert "analyst failed" in result["error"]
    assert orch.cache.stored == []


def test_deploy_failure_returns_error(monkeypatch):
    orch = _orch(monkeypatch, deploy_ok=False)
    result = orch._pipeline_repo(_env(), source="search_api")

    assert result["ok"] is False
    assert "deploy failed" in result["error"]


# ---------------- run_repo ----------------

def test_run_repo_rejects_invalid_url():
    result = _bare().run_repo("这不是一个仓库")
    assert result["ok"] is False
    assert "不是合法的 GitHub 仓库链接" in result["message"]


def test_run_repo_success_archives_document(monkeypatch, tmp_path):
    orch = _orch(monkeypatch, gate="pass")
    monkeypatch.setattr(orch_mod, "OUTPUTS_DIR", tmp_path)

    result = orch.run_repo("a/b")

    assert result["ok"] is True
    assert result["gate_result"] == "pass"
    from pathlib import Path

    written = list(Path(tmp_path).rglob("a_b.md"))
    assert written, "应归档到 outputs/YYYY-MM-DD/a_b.md"
    text = written[0].read_text(encoding="utf-8")
    assert "# a/b 新手解读" in text


def test_run_repo_failure_returns_degrade_message(monkeypatch):
    orch = _orch(monkeypatch, llm=None)
    result = orch.run_repo("a/b")

    assert result["ok"] is False
    assert "降级交付" in result["message"]
    assert "LLM_BASE_URL" in result["message"]


# ---------------- run_daily ----------------

def test_run_daily_degrades_when_no_repos(monkeypatch):
    orch = _orch(monkeypatch)
    monkeypatch.setattr(orch_mod.trending, "fetch_trending", lambda *a, **k: ([], "trending_page"))

    result = orch.run_daily(top_n=5)

    assert result["ok"] is False
    assert "热门榜单获取" in result["message"]


def test_run_daily_clamps_parse_count_to_max(monkeypatch):
    """top 异常大时必须被钳制，否则会对全部仓库跑 LLM，放大成巨额账单（C4）。

    注意区分两个量：候选池规模（pool，可大于 top）与自动解析数量（top，必须被钳制）。
    这里断言的是**实际调用 LLM 流水线的次数**。
    """
    repos = [{"full_name": f"o/r{i}"} for i in range(200)]
    orch = _orch(monkeypatch)
    monkeypatch.setattr(orch_mod.trending, "fetch_trending", lambda *a, **k: (repos, "search_api"))

    parsed: list[str] = []
    monkeypatch.setattr(orch, "_pipeline_repo",
                        lambda env, source: parsed.append(env.repo_full_name)
                        or {"ok": False, "repo": env.repo_full_name, "error": "skip"})
    monkeypatch.setattr(orch_mod.candidates, "build_day_snapshot",
                        lambda r, s, d: {"count": len(r), "items": []})
    monkeypatch.setattr(orch_mod.candidates, "save", lambda d, s: None)
    monkeypatch.setattr(orch_mod.candidates, "cleanup", lambda: [])
    monkeypatch.setattr(orch_mod.maintenance, "auto_prune", lambda _d: None)

    orch.run_daily(top_n=100000)

    assert len(parsed) == MAX_AUTO_PARSE, f"解析了 {len(parsed)} 个，应被钳制到 {MAX_AUTO_PARSE}"


def test_run_daily_pool_size_not_limited_by_top(monkeypatch):
    """候选池规模与解析数量解耦：池子可以比 top 大（v1.8 设计）。"""
    orch = _orch(monkeypatch)
    seen: dict = {}

    def fake_fetch(_client, size):
        seen["size"] = size
        return [], "trending_page"

    monkeypatch.setattr(orch_mod.trending, "fetch_trending", fake_fetch)
    orch.run_daily(top_n=3)

    assert seen["size"] == orch.settings.candidate_pool_size
    assert seen["size"] > 3


def test_run_daily_uses_trending_snapshot_cache(monkeypatch):
    repos = [{"full_name": f"o/r{i}"} for i in range(3)]
    orch = _orch(monkeypatch)
    orch.cache = FakeCache(trending={"repos": repos, "source": "search_api"})
    monkeypatch.setattr(orch_mod.trending, "fetch_trending",
                        lambda *a, **k: pytest.fail("命中快照时不应重新抓取"))

    orch.run_daily(top_n=1)
    # 走到候选池写入即说明用了快照；不校验返回值细节


def test_run_daily_writes_candidate_pool(monkeypatch, tmp_path):
    repos = [{"full_name": "o/r", "description": "d", "language": "Python",
              "stars": 1, "topics": [], "html_url": "https://github.com/o/r"}]
    orch = _orch(monkeypatch)
    monkeypatch.setattr(orch_mod.trending, "fetch_trending", lambda *a, **k: (repos, "search_api"))
    monkeypatch.setattr(orch_mod.candidates, "build_day_snapshot",
                        lambda r, s, d: {"count": len(r), "items": r})
    saved: list = []
    monkeypatch.setattr(orch_mod.candidates, "save", lambda d, s: saved.append((d, s)))
    monkeypatch.setattr(orch_mod.candidates, "cleanup", lambda: [])
    monkeypatch.setattr(orch_mod.translate, "translate_items", lambda items: 0)
    monkeypatch.setattr(orch_mod.maintenance, "auto_prune", lambda _d: None)

    orch.run_daily(top_n=1)

    assert saved, "候选池必须落盘，即使后续解析失败"
    assert saved[0][1]["count"] == 1
