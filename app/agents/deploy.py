"""DeployAgent（agent/DeployAgent.md）：补全 M5「本地一键部署完整方案」。

v1.5 关键修复：此前只把一键脚本与风险提示追加到 Analyst 的骨架后面，
LLM 生成的 `env_requirements`（逐项安装教程）与 `steps`（分系统分步命令）
被丢弃，导致最终文档残留「待 DeployAgent 补全」占位符。
现在改为**结构化字段确定性渲染**成完整 M5 正文，骨架不再进入终稿。

- 静态校验五项由代码执行（design.md §10），结果写入 DeployPlan.static_check。
- 报错大全（原 M6）已随 Req5 删除。
"""
from __future__ import annotations

import json

from .. import log, prompts, static_check
from ..contracts import DeployPlan, DraftDoc, RepoMeta
from ..llm import LLMClient, LLMError

_PLATFORM_TITLE = (("windows", "Windows"), ("macos", "macOS"), ("linux", "Linux"))


def build_user_payload(meta: RepoMeta, draft: DraftDoc) -> str:
    payload = {
        "full_name": meta.full_name,
        "language": meta.language,
        "description": meta.description,
        "readme_deploy_hints": meta.readme[:6000],
        "dependency_files": meta.deploy_hints,   # DeployAgent §2：依赖文件、启动脚本、配置项
        "analyst_deploy_notes": draft.modules.get("deploy", ""),
        "analyst_notes": draft.notes,
    }
    return json.dumps(payload, ensure_ascii=False)


def _render_env_requirements(items: list[dict]) -> list[str]:
    """① 环境准备：每项依赖附完整安装教程（怎么下载 / 怎么装 / 怎么验证）。"""
    lines = ["### ① 环境准备", ""]
    if not items:
        lines += ["本项目无需额外安装依赖，可直接进行下一步。", ""]
        return lines

    for i, item in enumerate(items, 1):
        # 先 strip 再兜底：`"  "` 是 truthy，用 `or` 兜底会漏掉「只有空白」的值，
        # 导致 M5 里渲染出空名称/空版本（v1.8.3 修复）
        name = str(item.get("name") or "").strip() or "未命名依赖"
        version = str(item.get("version") or "").strip() or "版本未明确"
        guide = str(item.get("install_guide") or "").strip()
        lines += [f"#### {i}. {name}（需要 {version}）", ""]
        lines += [guide if guide else "【注意】该依赖的安装教程缺失，请以仓库 README 为准。", ""]
    return lines


def _render_steps(steps: dict) -> list[str]:
    """② 分系统分步命令：每步含「做什么 → 命令 → 在哪执行 → 预期结果」。"""
    lines = ["### ② 分系统部署步骤", ""]
    for key, title in _PLATFORM_TITLE:
        items = steps.get(key) or []
        lines += [f"#### {title}", ""]
        if not items:
            lines += ["（该平台步骤缺失，请以仓库 README 为准）", ""]
            continue
        for n, step in enumerate(items, 1):
            lines += [f"{n}. {str(step).strip()}", ""]
    return lines


def _render_one_click(one_click: str) -> list[str]:
    """③ 一键部署脚本。"""
    lines = ["### ③ 一键部署脚本", ""]
    if not one_click:
        lines += ["本项目未提供一键脚本，请按上面的分步命令操作。", ""]
        return lines
    lines += [
        "```bash",
        one_click,
        "```",
        "",
        "**怎么用**：在项目根目录打开终端执行；执行后按脚本输出确认环境就绪。",
        "",
    ]
    return lines


def _render_run_check(run_check: list[dict]) -> list[str]:
    """④ 可运行性自检：逐条对照，全部打勾才算部署成功（V7 ③）。"""
    lines = ["### ④ 可运行性自检", "", "跑完后逐条对照，全部通过才算部署成功。", ""]
    if not run_check:
        lines += ["【注意】本次未生成自检清单，请按上面步骤的「预期看到什么」自行核对。", ""]
        return lines
    lines += ["| 检查项 | 预期结果 | 是否通过 |", "| --- | --- | --- |"]
    for item in run_check:
        step = str(item.get("step") or "").strip().replace("|", "/")
        expect = str(item.get("expect") or "").strip().replace("|", "/")
        lines.append(f"| {step} | {expect} | ☐ |")
    lines.append("")
    return lines


def _render_risks(risks: list[str]) -> list[str]:
    """⑤ 风险提示。"""
    lines = ["### ⑤ ⚠️ 风险提示", ""]
    if risks:
        lines += [f"- {str(r).strip()}" for r in risks]
    else:
        lines += ["- 暂无特别风险项，仍请注意不要以管理员身份运行来源不明的脚本。"]
    lines.append("")
    return lines


def build_m5(env_requirements: list[dict], steps: dict, one_click: str,
             run_check: list[dict], risks: list[str]) -> str:
    """把 DeployAgent 的结构化产出渲染为完整可运行的 M5 正文。"""
    lines: list[str] = [
        "> 本方案面向零基础新手：每一步都给出完整命令、执行位置与预期结果。",
        f"> {static_check.UNVERIFIED_NOTE}",
        "",
    ]
    lines += _render_env_requirements(env_requirements)
    lines += _render_steps(steps)
    lines += _render_one_click(one_click)
    lines += _render_run_check(run_check)
    lines += _render_risks(risks)
    return "\n".join(lines).strip()


def run(llm: LLMClient, meta: RepoMeta, draft: DraftDoc) -> tuple[DeployPlan, str]:
    log.console(f"  [部署] {meta.full_name}：生成三平台步骤、安装教程与一键脚本")
    raw = llm.chat(prompts.deploy_system(), build_user_payload(meta, draft), json_mode=True)
    data = llm.extract_json(raw)

    steps = data.get("steps") or {}
    for platform in ("windows", "macos", "linux"):
        if not isinstance(steps.get(platform), list) or not steps[platform]:
            raise LLMError(f"Deploy 产出缺少 {platform} 步骤（NFR8 三平台覆盖）")

    env_requirements = data.get("env_requirements") or []
    one_click = str(data.get("one_click_script", "")).strip()
    run_check = data.get("run_check") or []
    risks = [str(r) for r in (data.get("risks") or [])]

    # 先渲染完整 M5 正文，再做静态校验——校验项⑤（可复现）依赖 M5 正文中的
    # 「执行位置 / 预期结果」描述；若先传空串，该项恒失败、result 永远为 warning（v1.8 修复）。
    m5_full = build_m5(env_requirements, steps, one_click, run_check, risks)

    # 静态校验（无沙箱，design.md §10）
    check_result = static_check.check(steps, one_click, risks, m5_full)

    plan = DeployPlan(
        env_requirements=env_requirements,
        steps=steps,
        one_click_script=one_click,
        static_check=check_result,
        risks=risks,
        run_check=run_check,
        m5_markdown=m5_full,
    )
    return plan, m5_full
