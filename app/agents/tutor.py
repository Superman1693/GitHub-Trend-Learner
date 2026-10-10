"""TutorAgent（agent/TutorAgent.md）：新手语言转译 + 终审门禁（Quality Gate）。

- 终审执行 global.md §6.4 的 V1–V7（代码确定性判定 + LLM 语义判定）。
- 退回上限 2 次（global.md §6.2）；第 3 次仍不通过 → 降级交付并列出未达标项。
- 事实保护：不修改技术事实、命令、参数、版本号（约束注入在 prompts.TUTOR_CONTRACT）。
- 模块合并走 contracts.merge_modules：LLM 局部输出（修复轮只返回部分模块）不会丢内容。
"""
from __future__ import annotations

import json
from datetime import datetime

from .. import log, prompts, quality_gate
from ..contracts import DeployPlan, DraftDoc, FinalDoc, RepoMeta, merge_modules
from ..llm import LLMClient


def run(llm: LLMClient, meta: RepoMeta, draft: DraftDoc, plan: DeployPlan,
        m5_full: str, max_returns: int = 2) -> FinalDoc:
    log.console(f"  [终审] {meta.full_name}：新手语言转译 + V1–V7 门禁")
    system = prompts.tutor_system()
    modules_in = dict(draft.modules)
    modules_in["deploy"] = m5_full        # DeployAgent 补全后的 M5（完整可运行方案）
    payload = json.dumps({
        "full_name": meta.full_name,
        "project_type": draft.project_type,
        "upstream_notes": draft.notes,
        "modules": modules_in,
    }, ensure_ascii=False)

    raw = llm.chat(system, payload, json_mode=True)
    data = llm.extract_json(raw)
    modules = merge_modules(modules_in, data.get("modules"))
    glossary = data.get("glossary") or []
    attempts = 0
    rejected: list[dict] = []

    # 质量门禁循环：退回 ≤2 次（global.md §6.2）
    while True:
        issues = quality_gate.run_gate(modules, meta.html_url,
                                       upstream_notes=draft.notes)
        if not issues:
            gate_result = "pass"
            break
        if attempts >= max_returns:
            gate_result = "degraded"
            rejected = [
                {"module": i["module"], "check": i["check"], "issue": i["issue"],
                 "attempts": attempts}
                for i in issues
            ]
            log.console(f"  [终审] 退回 {attempts} 次后仍有 {len(issues)} 项未达标，执行降级交付")
            break
        attempts += 1
        log.console(f"  [终审] 门禁检出 {len(issues)} 项问题，第 {attempts}/{max_returns} 次退回修复")
        repair_user = (
            json.dumps({"issues": issues, "modules": modules}, ensure_ascii=False)
            + "\n\n" + prompts.REPAIR_CONTRACT
        )
        raw = llm.chat(system, repair_user, json_mode=True)
        data = llm.extract_json(raw)
        modules = merge_modules(modules, data.get("modules"))
        glossary = data.get("glossary") or glossary

    return FinalDoc(
        task_id="",
        repo_full_name=meta.full_name,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        modules=modules,
        gate_result=gate_result,
        rejected_items=rejected,
        glossary=glossary,
    )
