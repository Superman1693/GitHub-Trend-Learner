"""质量门禁 V1–V7（global.md §6.4，统一定义）。TutorAgent 终审时判定。

本模块实现可确定性判定的项（V1/V3/V5/V7 + V2/V4/V6 的代码侧启发式兜底）；
V2/V4/V6 的语义级判定由 Tutor LLM 在转译时执行，此处结果作为回归防护网。
"""
from __future__ import annotations

import re

from .contracts import MODULES_ORDER

# 套话词表基线（global.md §1.4）；单模块命中 ≥2 处即 V5 超标
CLICHE_WORDS = (
    "非常优秀", "众所周知", "总而言之", "不言而喻", "显而易见",
    "无可挑剔", "堪称完美", "强大到无需多言",
)

# 术语启发式词表（V2 兜底扫描）：命中后近距离内须有解释痕迹（（ 或 就像）
TERM_HINTS = (
    "API", "SDK", "CLI", "Docker", "容器", "虚拟环境",
    "解释器", "环境变量", "中间件", "包管理器", "注册表", "内核",
)

MIN_MODULE_LEN = 50

# 占位符特征（V7 ④）：上游骨架若未被补全，这些字样会残留在终稿里。
# 该缺陷曾导致「待 DeployAgent 补全」原样交付给用户，故设为门禁硬拦项。
PLACEHOLDER_PATTERNS = (
    r"待\s*DeployAgent", r"由\s*DeployAgent\s*(补全|填充|生成|给出)",
    r"待补全", r"待补", r"命令待补", r"待填充", r"待定稿", r"TODO", r"占位文本",
)


def _check_v1(modules: dict) -> list[dict]:
    issues = []
    for key, title in MODULES_ORDER:
        text = (modules.get(key) or "").strip()
        if len(text) < MIN_MODULE_LEN:
            issues.append({"check": "V1", "module": key,
                           "issue": f"模块缺失或内容过短（{title}，当前 {len(text)} 字符）",
                           "target": "RepoAnalystAgent"})
            continue
        # 模块正文不得使用 `##`（模块标题专用层级），否则会撑破模块边界，
        # 使阅读器的目录切分失效（v1.5 新增）。
        h2 = re.search(r"^##\s+\S", text, re.M)
        if h2:
            issues.append({"check": "V1", "module": key,
                           "issue": f"模块正文含二级标题「{h2.group(0).strip()}」，"
                                    f"应降级为 ### 或更深（模块边界为 ##）",
                           "target": "RepoAnalystAgent"})
    return issues


def _term_pattern(term: str) -> re.Pattern[str]:
    """术语匹配模式。

    英文术语必须整词匹配：早期用裸 `re.I` 子串匹配，导致「CLI」命中
    「Click here to download」里的「Cli」，产生假阳性并误判降级。
    中文术语无词边界概念，按子串匹配。
    """
    if term.isascii():
        return re.compile(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", re.I)
    return re.compile(re.escape(term))


def _strip_code_blocks(text: str) -> str:
    """去掉围栏代码块与行内代码：命令里的术语不需要解释（V2 只审正文）。"""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", " ", text)
    return text


def _check_v2(modules: dict) -> list[dict]:
    """术语启发式（V2 兜底）：每个术语只检查其在模块内的首次出现——
    global.md §1.2 要求首次出现即解释；首次已解释则该模块该词视为达标。"""
    issues = []
    for key, _ in MODULES_ORDER:
        text = _strip_code_blocks(modules.get(key) or "")
        for term in TERM_HINTS:
            m = _term_pattern(term).search(text)
            if not m:
                continue
            window = text[m.end():m.end() + 40]
            if "（" not in window and "(" not in window and "就像" not in window:
                issues.append({"check": "V2", "module": key,
                               "issue": f"术语「{term}」首次出现处未按 §1.2 格式解释",
                               "target": "RepoAnalystAgent"})
    return issues


def _check_v3(modules: dict) -> list[dict]:
    issues = []
    deploy = modules.get("deploy") or ""
    if not re.search(r"执行位置|在哪个目录|执行后|预期", deploy):
        issues.append({"check": "V3", "module": "deploy",
                       "issue": "命令缺少执行位置或预期结果说明（global.md §3.1）",
                       "target": "DeployAgent"})
    for key, _ in MODULES_ORDER:
        for block in re.findall(r"```(?:bash|sh|shell|powershell|bat)?\r?\n(.*?)```",
                                modules.get(key) or "", re.S):
            if not block.strip():
                issues.append({"check": "V3", "module": key,
                               "issue": "存在空命令代码块", "target": "DeployAgent"})
            if re.search(r"最新版|latest(?![_\w])", block, re.I):
                issues.append({"check": "V3", "module": key,
                               "issue": "命令使用「最新版/latest」，未给明确版本（global.md §3.3）",
                               "target": "DeployAgent"})
    return issues


def _check_v4(modules: dict, upstream_notes: list[str] | None) -> list[dict]:
    """V4：仅当上游标注了【注意】notes（说明存在不确定项）时，才要求终稿保留标注。
    global.md §4.1 的语义是「信息不确定时必须标注」，并非要求全文必须有标注。"""
    issues = []
    if upstream_notes and "【注意】" not in "\n".join(modules.values()):
        issues.append({"check": "V4", "module": "-",
                       "issue": "上游 notes 存在不确定项，但全文无任何【注意】标注，风险提示可能被删除（global.md §4.1）",
                       "target": "TutorAgent"})
    return issues


def _check_v5(modules: dict) -> list[dict]:
    issues = []
    for key, _ in MODULES_ORDER:
        text = modules.get(key) or ""
        hits = [w for w in CLICHE_WORDS if w in text]
        if len(hits) >= 2:
            issues.append({"check": "V5", "module": key,
                           "issue": f"套话超标（命中 {len(hits)} 处：{hits}，阈值 2，global.md §1.4）",
                           "target": "RepoAnalystAgent"})
    return issues


def _check_v6(modules: dict) -> list[dict]:
    issues = []
    deploy = modules.get("deploy") or ""
    if "环境准备" not in deploy:
        issues.append({"check": "V6", "module": "deploy",
                       "issue": "缺少环境准备清单，前置操作未补齐（Req3.5）",
                       "target": "DeployAgent"})
    tutorial = modules.get("tutorial") or ""
    if "极简" not in tutorial:
        issues.append({"check": "V6", "module": "tutorial",
                       "issue": "缺少「极简快速上手」版本（Req3.3）",
                       "target": "RepoAnalystAgent"})
    return issues


def _check_v7(modules: dict) -> list[dict]:
    """V7 部署可运行性（global.md §6.4，五项判定）。"""
    issues = []
    deploy = modules.get("deploy") or ""
    target = "DeployAgent"

    # ① 三平台步骤齐备
    for platform in ("Windows", "macOS", "Linux"):
        if platform.lower() not in deploy.lower():
            issues.append({"check": "V7", "module": "deploy",
                           "issue": f"缺少 {platform} 平台步骤（NFR8）", "target": target})

    # ② 环境准备附安装教程
    if "环境准备" not in deploy:
        issues.append({"check": "V7", "module": "deploy",
                       "issue": "缺少环境准备清单（global.md §2.1 M5 必含要素①）", "target": target})
    elif not re.search(r"怎么下载|下载地址|安装教程|怎么安装|安装步骤", deploy):
        issues.append({"check": "V7", "module": "deploy",
                       "issue": "环境准备未附安装教程（仅列名称与版本号不合格）", "target": target})

    # ③ 关键步骤给出「预期看到什么」
    if not re.search(r"应该看到|预期看到|预期结果|执行后.*看到|应该出现", deploy):
        issues.append({"check": "V7", "module": "deploy",
                       "issue": "关键步骤缺少「预期看到什么」，新手无法自检", "target": target})

    # ④ 无未说明来源的占位符
    for pattern in PLACEHOLDER_PATTERNS:
        if re.search(pattern, deploy):
            issues.append({"check": "V7", "module": "deploy",
                           "issue": f"存在未补全的占位符（匹配「{pattern}」），部署方案不可用",
                           "target": target})
            break

    # ⑤ 静态校验结果与风险提示齐备
    if "风险" not in deploy:
        issues.append({"check": "V7", "module": "deploy",
                       "issue": "缺少风险提示小节（Req4.7）", "target": target})
    if "未经实际执行验证" not in deploy:
        issues.append({"check": "V7", "module": "deploy",
                       "issue": "缺少「本命令未经实际执行验证」标注（global.md §3.2）",
                       "target": target})
    return issues


def run_gate(modules: dict, html_url: str = "",
             upstream_notes: list[str] | None = None) -> list[dict]:
    """执行 V1–V7，返回问题清单；空列表即通过。upstream_notes 为上游 DraftDoc.notes。"""
    issues: list[dict] = []
    issues += _check_v1(modules)
    issues += _check_v2(modules)
    issues += _check_v3(modules)
    issues += _check_v4(modules, upstream_notes)
    issues += _check_v5(modules)
    issues += _check_v6(modules)
    issues += _check_v7(modules)
    return issues
