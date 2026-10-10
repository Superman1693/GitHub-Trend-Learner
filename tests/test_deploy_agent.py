"""DeployAgent（app/agents/deploy.py）测试。

M5「本地一键部署完整方案」是项目的质量重心（global.md §6.4 V7 专为它设）。
这里覆盖两件事：
1. `build_m5` 的结构化渲染 —— 空值兜底、表格转义、三平台缺失提示；
2. `run` 的三平台强制校验，以及**静态校验必须拿到完整 M5 正文**
   （CODE_REVIEW.md C1 的回归点，传空串会让 result 恒为 warning）。
"""
from __future__ import annotations

import json

import pytest

from app.agents import deploy
from app.contracts import MODULE_KEYS, DraftDoc, RepoMeta
from app.llm import LLMClient, LLMError


class FakeLLM:
    last_usage_total = 9

    def __init__(self, reply: dict) -> None:
        self._reply = reply
        self.calls: list[str] = []

    def chat(self, system: str, user: str, temperature: float = 0.3,
             json_mode: bool = False) -> str:
        self.calls.append(user)
        return json.dumps(self._reply, ensure_ascii=False)

    extract_json = staticmethod(LLMClient.extract_json)


def _meta() -> RepoMeta:
    return RepoMeta(full_name="a/b", html_url="https://github.com/a/b", description="演示",
                    stars=1, forks=0, language="Python", license="MIT", topics=[],
                    default_branch="main", head_sha="a" * 40, fetched_at="2026-10-10 10:00",
                    source="search_api", readme="R" * 9000, tree=[], core_files=[],
                    deploy_hints=[{"path": "requirements.txt", "content": "requests"}],
                    degraded=True, degrade_reason="目录树过大")


def _draft() -> DraftDoc:
    return DraftDoc(project_type="tool",
                    modules={k: f"{k} 正文" for k in MODULE_KEYS},
                    notes=["【注意】某处不确定"])


def _reply(**over) -> dict:
    base = {
        "env_requirements": [{"name": "Python", "version": "3.12",
                              "install_guide": "去 python.org 下载 → 安装 → 输入 python -V 验证"}],
        "steps": {"windows": ["在终端执行 winget install Python"],
                  "macos": ["在终端执行 brew install python@3.12"],
                  "linux": ["在终端执行 apt-get install python3.12"]},
        "one_click_script": "pip install -r requirements.txt",
        "run_check": [{"step": "启动", "expect": "看到监听日志"}],
        "risks": ["不要以管理员身份运行来源不明的脚本"],
    }
    base.update(over)
    return base


# ---------------- build_user_payload ----------------

def test_payload_includes_deploy_hints_and_notes():
    payload = json.loads(deploy.build_user_payload(_meta(), _draft()))
    assert payload["dependency_files"][0]["path"] == "requirements.txt"
    assert payload["analyst_deploy_notes"] == "deploy 正文"
    assert payload["analyst_notes"] == ["【注意】某处不确定"]


def test_payload_truncates_readme_to_6000():
    payload = json.loads(deploy.build_user_payload(_meta(), _draft()))
    assert len(payload["readme_deploy_hints"]) == 6000


# ---------------- 渲染：环境准备 ----------------

def test_render_env_requirements_lists_install_guides():
    lines = deploy._render_env_requirements(
        [{"name": "Node", "version": "20", "install_guide": "去官网下载安装"}])
    text = "\n".join(lines)
    assert "① 环境准备" in text
    assert "#### 1. Node（需要 20）" in text
    assert "去官网下载安装" in text


def test_render_env_requirements_handles_empty():
    text = "\n".join(deploy._render_env_requirements([]))
    assert "无需额外安装依赖" in text


def test_render_env_requirements_warns_on_missing_guide():
    text = "\n".join(deploy._render_env_requirements([{"name": "Go", "version": "1.22"}]))
    assert "【注意】" in text and "安装教程缺失" in text


def test_render_env_requirements_falls_back_for_blank_name_and_version():
    text = "\n".join(deploy._render_env_requirements([{"name": "  ", "version": ""}]))
    assert "未命名依赖" in text and "版本未明确" in text


# ---------------- 渲染：分系统步骤 ----------------

def test_render_steps_covers_three_platforms_in_order():
    text = "\n".join(deploy._render_steps({"windows": ["w"], "macos": ["m"], "linux": ["l"]}))
    assert text.index("#### Windows") < text.index("#### macOS") < text.index("#### Linux")
    assert "1. w" in text and "1. m" in text and "1. l" in text


def test_render_steps_marks_missing_platform():
    text = "\n".join(deploy._render_steps({"windows": ["w"], "macos": [], "linux": ["l"]}))
    assert "该平台步骤缺失" in text


# ---------------- 渲染：一键脚本 ----------------

def test_render_one_click_wraps_in_code_block():
    text = "\n".join(deploy._render_one_click("pip install x"))
    assert "```bash" in text and "pip install x" in text
    assert "怎么用" in text


def test_render_one_click_handles_empty():
    text = "\n".join(deploy._render_one_click(""))
    assert "未提供一键脚本" in text


# ---------------- 渲染：自检清单 ----------------

def test_render_run_check_builds_table_with_checkboxes():
    text = "\n".join(deploy._render_run_check([{"step": "启动", "expect": "看到日志"}]))
    assert "| 检查项 | 预期结果 | 是否通过 |" in text
    assert "| 启动 | 看到日志 | ☐ |" in text


def test_render_run_check_escapes_pipe_in_cells():
    """单元格里的 | 会撑破 Markdown 表格，必须转义。"""
    text = "\n".join(deploy._render_run_check([{"step": "a|b", "expect": "c|d"}]))
    assert "a/b" in text and "c/d" in text


def test_render_run_check_handles_empty():
    text = "\n".join(deploy._render_run_check([]))
    assert "未生成自检清单" in text


# ---------------- 渲染：风险提示 ----------------

def test_render_risks_lists_items():
    text = "\n".join(deploy._render_risks(["有风险 A", "有风险 B"]))
    assert "- 有风险 A" in text and "- 有风险 B" in text


def test_render_risks_has_default_when_empty():
    text = "\n".join(deploy._render_risks([]))
    assert "暂无特别风险项" in text


# ---------------- build_m5 组装 ----------------

def test_build_m5_contains_all_five_sections():
    text = deploy.build_m5(
        [{"name": "Python", "version": "3.12", "install_guide": "装它"}],
        {"windows": ["w"], "macos": ["m"], "linux": ["l"]},
        "echo hi", [{"step": "s", "expect": "e"}], ["风险"])
    for anchor in ("① 环境准备", "② 分系统部署步骤", "③ 一键部署脚本",
                   "④ 可运行性自检", "⑤ ⚠️ 风险提示"):
        assert anchor in text
    assert "未经实际执行验证" in text, "必须带未验证声明（global.md §3.2）"


# ---------------- run：三平台强制校验 ----------------

@pytest.mark.parametrize("missing", ["windows", "macos", "linux"])
def test_run_requires_all_three_platforms(missing):
    steps = {"windows": ["w"], "macos": ["m"], "linux": ["l"]}
    steps[missing] = []
    with pytest.raises(LLMError) as exc:
        deploy.run(FakeLLM(_reply(steps=steps)), _meta(), _draft())
    assert missing in str(exc.value)


def test_run_requires_platform_key_present():
    steps = {"windows": ["w"], "macos": ["m"]}          # 缺 linux 键
    with pytest.raises(LLMError):
        deploy.run(FakeLLM(_reply(steps=steps)), _meta(), _draft())


def test_run_raises_when_steps_missing_entirely():
    reply = _reply()
    reply.pop("steps")
    with pytest.raises(LLMError):
        deploy.run(FakeLLM(reply), _meta(), _draft())


# ---------------- run：静态校验必须拿到完整 M5（C1 回归） ----------------

def test_run_static_check_receives_full_m5_and_can_pass():
    """回归 CODE_REVIEW.md C1：若给 static_check 传空串，result 会恒为 warning。"""
    plan, m5 = deploy.run(FakeLLM(_reply()), _meta(), _draft())

    assert plan.static_check["result"] == "pass", (
        f"合规内容应通过静态校验，实际 issues={plan.static_check['issues']}"
    )
    assert plan.static_check["issues"] == []
    # 校验项⑤依赖 M5 正文中的「执行位置/预期结果」，故 m5 必须非空且被传入
    assert m5 and "执行位置" in m5


def test_run_static_check_flags_placeholders():
    """含占位符的脚本必须被静态校验拦下（V7 ④）。"""
    plan, _ = deploy.run(FakeLLM(_reply(one_click_script="pip install <待补全>")),
                         _meta(), _draft())
    assert plan.static_check["result"] == "warning"
    assert any("占位符" in i["detail"] for i in plan.static_check["issues"])


def test_run_returns_plan_with_all_fields():
    plan, m5 = deploy.run(FakeLLM(_reply()), _meta(), _draft())
    assert plan.one_click_script.startswith("pip install")
    assert plan.steps["windows"]
    assert plan.run_check[0]["step"] == "启动"
    assert plan.risks
    assert plan.m5_markdown == m5


def test_run_tolerates_missing_optional_fields():
    reply = _reply()
    for key in ("env_requirements", "run_check", "risks", "one_click_script"):
        reply.pop(key)
    plan, m5 = deploy.run(FakeLLM(reply), _meta(), _draft())
    assert plan.env_requirements == []
    assert plan.risks == []
    assert "未提供一键脚本" in m5
