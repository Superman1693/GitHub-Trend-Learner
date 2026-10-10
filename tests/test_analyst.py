"""RepoAnalystAgent（app/agents/analyst.py）测试。

此前覆盖率 30%。它的契约校验（缺模块即违约、非法 project_type 归零）
是流水线的第一道闸门，出错会让下游拿到残缺 DraftDoc。
"""
from __future__ import annotations

import json

import pytest

from app.agents import analyst
from app.contracts import MODULE_KEYS, PROJECT_TYPES, RepoMeta
from app.llm import LLMClient, LLMError


class FakeLLM:
    last_usage_total = 5

    def __init__(self, reply: dict) -> None:
        self._reply = reply
        self.calls: list[str] = []

    def chat(self, system: str, user: str, temperature: float = 0.3,
             json_mode: bool = False) -> str:
        self.calls.append(user)
        return json.dumps(self._reply, ensure_ascii=False)

    # analyst.run 会调用它，复用真实实现以保证解析行为一致
    extract_json = staticmethod(LLMClient.extract_json)


def _meta(degraded: bool = False) -> RepoMeta:
    return RepoMeta(
        full_name="a/b", html_url="https://github.com/a/b", description="一个演示仓库",
        stars=10, forks=1, language="Python", license="MIT", topics=["cli"],
        default_branch="main", head_sha="a" * 40, fetched_at="2026-10-10 10:00",
        source="search_api", readme="# README", tree=[f"src/f{i}.py" for i in range(300)],
        core_files=[{"path": "src/main.py", "content": "print(1)"}],
        degraded=degraded, degrade_reason="目录树过大" if degraded else "",
    )


def _reply(project_type="tool", modules=None, **extra) -> dict:
    return {
        "project_type": project_type,
        "modules": modules if modules is not None
        else {k: f"{k} 的正文内容" for k in MODULE_KEYS},
        **extra,
    }


# ---------------- build_user_payload ----------------

def test_payload_is_valid_json_with_core_fields():
    payload = json.loads(analyst.build_user_payload(_meta()))
    assert payload["full_name"] == "a/b"
    assert payload["readme"] == "# README"
    assert payload["core_files"][0]["path"] == "src/main.py"
    assert payload["topics"] == ["cli"]


def test_payload_truncates_tree_to_200_entries():
    """目录树必须裁剪，否则超长树会撑爆上下文（§8.3）。"""
    payload = json.loads(analyst.build_user_payload(_meta()))
    assert len(payload["tree"]) == 200


def test_payload_carries_degrade_flag():
    payload = json.loads(analyst.build_user_payload(_meta(degraded=True)))
    assert payload["degraded"] is True
    assert payload["degrade_reason"] == "目录树过大"


# ---------------- run 正常路径 ----------------

def test_run_returns_draft_with_all_modules():
    draft = analyst.run(FakeLLM(_reply()), _meta())
    assert set(draft.modules) >= set(MODULE_KEYS)
    assert draft.project_type == "tool"


@pytest.mark.parametrize("ptype", PROJECT_TYPES)
def test_run_accepts_all_declared_project_types(ptype):
    draft = analyst.run(FakeLLM(_reply(project_type=ptype)), _meta())
    assert draft.project_type == ptype


def test_run_normalises_unknown_project_type():
    """非法类型必须归零为 unknown，而不是让 DraftDoc 抛 ValueError。"""
    draft = analyst.run(FakeLLM(_reply(project_type="某种没见过的类型")), _meta())
    assert draft.project_type == "unknown"


def test_run_normalises_missing_project_type():
    reply = _reply()
    reply.pop("project_type")
    assert analyst.run(FakeLLM(reply), _meta()).project_type == "unknown"


# ---------------- run 契约违约 ----------------

@pytest.mark.parametrize("missing", MODULE_KEYS)
def test_run_raises_when_module_missing(missing):
    modules = {k: "内容" for k in MODULE_KEYS if k != missing}
    with pytest.raises(LLMError) as exc:
        analyst.run(FakeLLM(_reply(modules=modules)), _meta())
    assert missing in str(exc.value)


def test_run_raises_when_module_blank():
    modules = {k: "内容" for k in MODULE_KEYS}
    modules["intro"] = "   "
    with pytest.raises(LLMError):
        analyst.run(FakeLLM(_reply(modules=modules)), _meta())


def test_run_raises_when_modules_missing_entirely():
    reply = _reply()
    reply.pop("modules")
    with pytest.raises(LLMError):
        analyst.run(FakeLLM(reply), _meta())


# ---------------- run 的 notes 处理 ----------------

def test_run_keeps_notes_as_strings():
    draft = analyst.run(FakeLLM(_reply(notes=["不确定 A", 123])), _meta())
    assert draft.notes == ["不确定 A", "123"], "非字符串 note 应被强制转字符串"


def test_run_injects_degrade_note_first():
    """降级解析必须在上游 notes 首位插入【注意】，供门禁 V4 校验。"""
    draft = analyst.run(FakeLLM(_reply(notes=["原有注意"])), _meta(degraded=True))

    assert draft.notes[0].startswith("【注意】")
    assert "目录树过大" in draft.notes[0]
    assert "原有注意" in draft.notes


def test_run_does_not_inject_note_when_not_degraded():
    draft = analyst.run(FakeLLM(_reply(notes=[])), _meta())
    assert draft.notes == []


def test_run_collects_open_questions():
    draft = analyst.run(FakeLLM(_reply(open_questions=["需要确认许可证"])), _meta())
    assert draft.open_questions == ["需要确认许可证"]


def test_run_tolerates_null_optional_fields():
    draft = analyst.run(FakeLLM(_reply(notes=None, open_questions=None)), _meta())
    assert draft.notes == [] and draft.open_questions == []


def test_run_sends_payload_to_llm():
    llm = FakeLLM(_reply())
    analyst.run(llm, _meta())
    assert len(llm.calls) == 1
    assert "a/b" in llm.calls[0]
