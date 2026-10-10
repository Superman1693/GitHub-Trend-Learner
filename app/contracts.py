"""Agent 间数据契约（design.md §5）。上游必须产出、下游必须消费；缺字段视为交接违约。

字段定义与 design.md §5.1–§5.5 一致。`DeployPlan.m5_markdown` 是 design.md §4 时序
「Deploy → Orchestrator : DeployPlan（含 M5 完整内容）」中 M5 正文的载体。
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

MODES = ("daily_trend", "custom_repo")

# 项目类型枚举与中文标签：**全项目唯一来源**（v1.8 收敛）。
# 早期在 contracts / analyst / classify 三处各写一份，导致 classify 产出的 `resource`
# 不在契约枚举内、`script` 又永远不被产出。现统一在此定义，其余模块一律引用。
PROJECT_TYPES = ("tool", "ai_model", "framework", "script", "template", "resource", "unknown")

PROJECT_TYPE_LABELS: dict[str, str] = {
    "tool": "工具 / 应用",
    "ai_model": "AI 模型 / 应用",
    "framework": "框架 / 库",
    "script": "脚本 / 自动化",
    "template": "模板 / 脚手架",
    "resource": "资料 / 清单",
    "unknown": "未知",
}


def project_type_label(value: str | None) -> str:
    """把项目类型枚举转成中文标签；未知值原样回退（不抛错）。

    先 strip 再判断，避免 `"  "` 这类空白值被当成有效值返回（v1.8.3）。
    """
    key = (value or "").strip()
    return PROJECT_TYPE_LABELS.get(key) or (key or "未知")

# 六模块标准命名（global.md §2.1，唯一权威来源）
# v1.5：删除原 M6「部署与使用常见报错大全」，原 M7「新手学习提升指南」前移为 M6。
MODULES_ORDER: list[tuple[str, str]] = [
    ("intro", "一、项目基础大白话介绍"),
    ("principle", "二、零基础通俗原理讲解"),
    ("tutorial", "三、新手入门使用教程"),
    ("source-code", "四、源码核心逻辑通俗分析"),
    ("deploy", "五、本地一键部署完整方案"),
    ("growth", "六、新手学习提升指南"),
]
MODULE_KEYS = [k for k, _ in MODULES_ORDER]

_ORDINAL_PREFIX = re.compile(r"^[一二三四五六七八九十]+[、.．]\s*")


def module_specs() -> list[dict[str, str]]:
    """六模块规范（key + 去序号标题），供 API / 前端展示。

    前端「系统设置」页与任何需要展示模块清单的地方都应消费它，
    而不是各自硬编码一份（v1.8 收敛，此前前后端各有一份副本）。
    """
    return [{"key": key, "name": _ORDINAL_PREFIX.sub("", title)}
            for key, title in MODULES_ORDER]


def merge_modules(base: dict | None, new: dict | None) -> dict:
    """合并模块字典：new 中非空字符串覆盖 base，缺失/空值保留 base。

    防止 LLM 局部输出（修复轮只返回部分模块）导致整包内容丢失。
    """
    merged = dict(base or {})
    for key, value in (new or {}).items():
        if isinstance(value, str) and value.strip():
            merged[key] = value
    return merged


@dataclass
class TaskEnvelope:
    """任务信封（design.md §5.1，Orchestrator → 各 Agent）。"""

    task_id: str
    trace_id: str
    mode: str
    repo_full_name: str = ""
    attempt: int = 0
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f"非法 mode：{self.mode}（应为 {MODES} 之一）")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RepoMeta:
    """采集产出（design.md §5.2，TrendCollectorAgent → RepoAnalystAgent）。

    `deploy_hints` 是 v1.4 实现对 §5.2 的补充字段，承载 DeployAgent §2 输入契约要求的
    「依赖文件、启动脚本、配置项等原始信息」。
    """

    full_name: str
    html_url: str
    description: str | None
    stars: int
    forks: int
    language: str | None
    license: str | None
    topics: list[str]
    default_branch: str
    head_sha: str
    fetched_at: str
    source: str                      # trending_page | search_api
    readme: str
    tree: list[str]
    core_files: list[dict]           # [{path, content}]，按 §5.6 规则筛选
    degraded: bool = False
    degrade_reason: str = ""
    deploy_hints: list[dict] = field(default_factory=list)  # [{path, content}] 依赖文件/启动脚本/配置项

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DraftDoc:
    """解析草稿（design.md §5.3，RepoAnalystAgent → DeployAgent / TutorAgent）。"""

    project_type: str
    modules: dict[str, str]
    notes: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.project_type not in PROJECT_TYPES:
            raise ValueError(f"非法 project_type：{self.project_type}")
        missing = [k for k in MODULE_KEYS if k not in self.modules]
        if missing:
            raise ValueError(f"DraftDoc 缺模块键：{missing}（交接违约，design.md §5.3）")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DeployPlan:
    """部署方案（design.md §5.4，DeployAgent 产出）。

    v1.5：移除 `error_kb_hits` 与 `m6_markdown`（报错大全已删除）；
    新增 `run_check` 承载「关键步骤 → 预期结果」自检表，支撑 global.md §6.4 校验项 V7。
    """

    env_requirements: list[dict]            # [{name, version, install_guide}]
    steps: dict[str, list[str]]             # {windows[], macos[], linux[]}
    one_click_script: str
    static_check: dict                      # {verified_by, result, unverified_reason, issues}
    risks: list[str]
    run_check: list[dict] = field(default_factory=list)   # [{step, expect}]
    m5_markdown: str = ""                   # M5 完整正文（design.md §4 时序载体）


@dataclass
class FinalDoc:
    """终稿（design.md §5.5，TutorAgent → Orchestrator）。"""

    task_id: str
    repo_full_name: str
    generated_at: str
    modules: dict[str, str]
    gate_result: str                         # pass | degraded
    rejected_items: list[dict]               # [{check, module, issue, attempts}]
    glossary: list[dict]                     # [{term, explain}]

    def __post_init__(self) -> None:
        if self.gate_result not in ("pass", "degraded"):
            raise ValueError(f"非法 gate_result：{self.gate_result}")
        missing = [k for k in MODULE_KEYS if k not in self.modules]
        if missing:
            raise ValueError(f"FinalDoc 缺模块键：{missing}（交接违约，design.md §5.5）")

    def to_dict(self) -> dict:
        return asdict(self)
