"""RepoAnalystAgent（agent/RepoAnalystAgent.md）：项目类型识别 + M1–M4、M6 生成 + M5 要点。

输入 RepoMeta，输出 DraftDoc（design.md §5.3）。M5 只写环境准备与步骤要点（完整可运行方案
与一键脚本属 DeployAgent）。LLM 未配置时抛 LLMNotConfigured，由编排层降级。
"""
from __future__ import annotations

import json

from ..contracts import PROJECT_TYPES, DraftDoc, RepoMeta
from .. import log
from ..llm import LLMClient, LLMError
from .. import prompts


def build_user_payload(meta: RepoMeta) -> str:
    """把 RepoMeta 组装为 LLM 输入（遵守上下文裁剪后的体积，§8.3）。"""
    payload = {
        "full_name": meta.full_name,
        "html_url": meta.html_url,
        "description": meta.description,
        "stars": meta.stars,
        "language": meta.language,
        "license": meta.license,
        "topics": meta.topics,
        "degraded": meta.degraded,
        "degrade_reason": meta.degrade_reason,
        "readme": meta.readme,
        "tree": meta.tree[:200],
        "core_files": meta.core_files,
    }
    return json.dumps(payload, ensure_ascii=False)


def run(llm: LLMClient, meta: RepoMeta) -> DraftDoc:
    log.console(f"  [解析] {meta.full_name}：识别项目类型并生成 M1–M4、M6 与 M5 要点")
    raw = llm.chat(prompts.analyst_system(), build_user_payload(meta), json_mode=True)
    data = llm.extract_json(raw)

    modules = data.get("modules") or {}
    for key in ("intro", "principle", "tutorial", "source-code", "deploy", "growth"):
        if not str(modules.get(key, "")).strip():
            raise LLMError(f"Analyst 产出缺少模块 {key}（交接违约，design.md §5.3）")

    project_type = data.get("project_type", "unknown")
    if project_type not in PROJECT_TYPES:   # 单一来源，见 contracts.PROJECT_TYPES
        project_type = "unknown"

    notes = [str(n) for n in (data.get("notes") or [])]
    if meta.degraded:
        notes.insert(0, f"【注意】因仓库体积限制，以下分析基于核心目录降级解析（{meta.degrade_reason}）")

    return DraftDoc(
        project_type=project_type,
        modules=modules,
        notes=notes,
        open_questions=[str(q) for q in (data.get("open_questions") or [])],
    )
