"""TutorAgent（app/agents/tutor.py）测试。

该模块此前覆盖率仅 19%，但它决定「通过 / 退回修复 / 降级交付」这条关键控制流：
退回次数算错会让质量不达标的文档被当成合格品缓存下来（v1.5 修过一次的坑）。

用假 LLM + 可控的门禁结果测试控制流，不触网、不依赖真实提示词效果。
"""
from __future__ import annotations

import json

import pytest

from app import quality_gate
from app.agents import tutor
from app.contracts import MODULES_ORDER, DeployPlan, DraftDoc, RepoMeta
from app.llm import LLMClient


class FakeLLM:
    """按序返回预设回复；记录每次调用，便于断言调用次数与内容。"""

    last_usage_total = 7

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[str] = []

    def chat(self, system: str, user: str, temperature: float = 0.3,
             json_mode: bool = False) -> str:
        self.calls.append(user)
        if not self._responses:
            raise AssertionError("FakeLLM 回复已用尽，说明调用次数超出预期")
        return self._responses.pop(0)

    extract_json = staticmethod(LLMClient.extract_json)


def _meta() -> RepoMeta:
    return RepoMeta(full_name="a/b", html_url="https://github.com/a/b", description="d",
                    stars=1, forks=0, language="Python", license="MIT", topics=[],
                    default_branch="main", head_sha="x" * 40, fetched_at="2026-10-10 10:00",
                    source="search_api", readme="", tree=[], core_files=[])


def _draft() -> DraftDoc:
    return DraftDoc(project_type="tool",
                    modules={k: f"{k} 正文" for k, _ in MODULES_ORDER},
                    notes=["【注意】某处不确定"])


def _plan() -> DeployPlan:
    return DeployPlan(env_requirements=[], steps={"windows": ["a"], "macos": ["b"], "linux": ["c"]},
                      one_click_script="echo hi", static_check={"result": "pass"},
                      risks=[], m5_markdown="M5 正文")


def _reply(modules: dict[str, str] | None = None, glossary=None) -> str:
    payload = {"modules": modules or {}, "glossary": glossary or []}
    return json.dumps(payload, ensure_ascii=False)


@pytest.fixture
def gate(monkeypatch):
    """用可控的门禁结果替换真实 V1–V7，专注测 tutor 的控制流。"""
    state = {"results": []}

    def fake_run_gate(modules, upstream_notes=None):
        return state["results"].pop(0) if state["results"] else []

    monkeypatch.setattr(quality_gate, "run_gate", fake_run_gate)
    return state


def test_passes_on_first_check_without_repair(gate):
    gate["results"] = [[]]                      # 首次即无问题
    llm = FakeLLM([_reply({"intro": "转译后的 M1"})])

    final = tutor.run(llm, _meta(), _draft(), _plan(), "M5", max_returns=2)

    assert final.gate_result == "pass"
    assert final.rejected_items == []
    assert len(llm.calls) == 1, "门禁通过时不应触发修复轮"
    assert final.modules["intro"] == "转译后的 M1"


def test_repairs_once_then_passes(gate):
    gate["results"] = [                                            # 第一次有问题
        [{"check": "V1", "module": "intro", "issue": "太短", "target": "RepoAnalystAgent"}],
        [],                                                        # 修复后通过
    ]
    llm = FakeLLM([_reply({"intro": "初稿"}), _reply({"intro": "修复稿"})])

    final = tutor.run(llm, _meta(), _draft(), _plan(), "M5", max_returns=2)

    assert final.gate_result == "pass"
    assert len(llm.calls) == 2
    assert final.modules["intro"] == "修复稿"
    assert "V1" in llm.calls[1], "修复请求里应带上待修问题"


def test_degrades_after_max_returns(gate):
    """始终有问题时，退回 max_returns 次后必须降级并列出未达标项。"""
    issue = [{"check": "V7", "module": "deploy", "issue": "缺风险提示", "target": "DeployAgent"}]
    gate["results"] = [issue, issue, issue]
    llm = FakeLLM([_reply({"intro": "v0"}), _reply({"intro": "v1"}), _reply({"intro": "v2"})])

    final = tutor.run(llm, _meta(), _draft(), _plan(), "M5", max_returns=2)

    assert final.gate_result == "degraded"
    assert len(llm.calls) == 3, "1 次初稿 + max_returns(2) 次修复"
    assert final.rejected_items and final.rejected_items[0]["check"] == "V7"
    assert final.rejected_items[0]["attempts"] == 2


def test_max_returns_zero_degrades_immediately(gate):
    gate["results"] = [[{"check": "V1", "module": "intro", "issue": "x", "target": "a"}]]
    llm = FakeLLM([_reply({"intro": "v0"})])

    final = tutor.run(llm, _meta(), _draft(), _plan(), "M5", max_returns=0)

    assert final.gate_result == "degraded"
    assert len(llm.calls) == 1, "max_returns=0 时不应有修复轮"


def test_partial_repair_does_not_lose_other_modules(gate):
    """LLM 修复轮只返回部分模块时，其余模块必须保留（contracts.merge_modules）。"""
    gate["results"] = [
        [{"check": "V1", "module": "intro", "issue": "太短", "target": "a"}],
        [],
    ]
    llm = FakeLLM([
        _reply({"intro": "初稿 intro", "growth": "初稿 growth"}),
        _reply({"intro": "只改了 intro"}),          # 只回一个模块
    ])

    final = tutor.run(llm, _meta(), _draft(), _plan(), "M5", max_returns=2)

    assert final.modules["intro"] == "只改了 intro"
    assert final.modules["growth"] == "初稿 growth", "未被修复的模块不应丢失"
    assert final.modules["deploy"] == "M5", "M5 应来自 DeployAgent 的完整正文"


def test_glossary_kept_when_repair_omits_it(gate):
    gate["results"] = [
        [{"check": "V1", "module": "intro", "issue": "x", "target": "a"}],
        [],
    ]
    llm = FakeLLM([
        _reply({"intro": "a"}, glossary=[{"term": "CLI", "explain": "命令行界面"}]),
        _reply({"intro": "b"}),                     # 修复轮没回 glossary
    ])

    final = tutor.run(llm, _meta(), _draft(), _plan(), "M5", max_returns=2)

    assert final.glossary == [{"term": "CLI", "explain": "命令行界面"}]


def test_returns_all_six_modules(gate):
    gate["results"] = [[]]
    llm = FakeLLM([_reply({k: f"{k}-正文" for k, _ in MODULES_ORDER})])

    final = tutor.run(llm, _meta(), _draft(), _plan(), "M5", max_returns=2)

    for key, _ in MODULES_ORDER:
        assert final.modules.get(key), f"缺少模块 {key}"
    assert final.repo_full_name == "a/b"
