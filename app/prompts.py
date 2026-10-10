"""提示词资产装载（design.md §14）。agent/*.md、global.md 为唯一内容来源，不复制进代码。

每个 LLM 环节的系统提示词 = 对应 Agent 提示词 + global.md 全局规则 + 严格 JSON 输出契约
（契约字段与 design.md §5.3/§5.4/§5.5 一致）。
"""
from __future__ import annotations

from .config import PROJECT_ROOT


def _read(rel: str) -> str:
    return (PROJECT_ROOT / rel).read_text(encoding="utf-8")


def load_global() -> str:
    return _read("global.md")


def load_agent(name: str) -> str:
    return _read(f"agent/{name}.md")


ANALYST_CONTRACT = """
## 输出契约（严格执行，输出单个 JSON 对象，不要输出其他文字）

```json
{
  "project_type": "tool | ai_model | framework | script | template | resource | unknown",
  "modules": {
    "intro": "M1 的完整 Markdown 正文（不含模块标题，标题由模板统一加）",
    "principle": "M2 的完整 Markdown 正文",
    "tutorial": "M3 的完整 Markdown 正文",
    "source-code": "M4 的完整 Markdown 正文（基于给定 core_files，引用需标注文件路径）",
    "deploy": "M5 的环境准备要点与分系统步骤要点（禁止生成一键部署脚本，脚本由 DeployAgent 负责）",
    "growth": "M6 的完整 Markdown 正文"
  },
  "notes": ["【注意】不确定项 + 风险"],
  "open_questions": []
}
```

硬性要求：
1. 模块内容遵守 global.md §1（大白话、术语首次出现附「术语（一句话解释，就像……）」）。
2. 按项目类型定制内容重点（global.md §2.2），禁止套用同一套话术。
3. deploy 模块只写环境准备与步骤**要点**，供 DeployAgent 补全为可运行方案；
   一键脚本由 DeployAgent 生成，你不得越界（global.md §5.1）。
   **禁止写「待补全」「待 DeployAgent 填充」这类占位符**——你写的是要点，不是空壳。
4. **标题层级**：模块正文内部只能用 `###` 及更深层级（`####`、`#####`）。
   严禁在模块正文里使用 `##`——`##` 是模块标题专用层级，越级会撑破模块边界。
5. 禁止编造仓库信息、命令、版本号；不确定写入 notes（global.md §4.1）。
"""

DEPLOY_CONTRACT = """
## 输出契约（严格执行，输出单个 JSON 对象，不要输出其他文字）

```json
{
  "env_requirements": [
    {"name": "依赖名称",
     "version": "明确版本或范围，禁止『最新版』",
     "install_guide": "安装教程：怎么下载 → 怎么安装（分 Windows/macOS/Linux）→ 怎么确认装好了（验证命令 + 预期输出）"}
  ],
  "steps": {
    "windows": ["每步格式：这一步做什么 → 完整命令 → 在哪个目录/窗口执行 → 执行后应该看到什么"],
    "macos": ["…"],
    "linux": ["…"]
  },
  "one_click_script": "一键部署脚本内容（bash；若项目仅支持 Windows 可用 PowerShell 并在 windows 步骤说明执行方式）",
  "run_check": [{"step": "关键步骤名", "expect": "应该看到什么"}],
  "risks": ["涉及 sudo、权限、防火墙、端口暴露等操作的风险提示"]
}
```

硬性要求：
1. **可运行**：命令必须完整可复制，除用户必须自行填写的值外不得出现占位符；
   每个待填值都要写明「在哪里获取」（global.md §2.1 M5 强化要求）。
2. **小白视角**：默认用户从未打开过终端。前置动作（打开终端、切换目录、创建虚拟环境）必须写进 steps。
3. `env_requirements` 每项的 `install_guide` 必须含三件事：怎么下载、怎么安装、怎么确认装好了。
   只写名称与版本号不合格。
4. `run_check` 至少 3 条，覆盖「环境是否就绪」「项目是否启动成功」「如何验证可用」。
5. **禁止写「待补全」「由 DeployAgent 补全」这类占位符**——你就是最终产出方。
6. 若项目无需传统部署（如纯文档仓库），env_requirements 写所需工具，
   steps 写「如何获取并使用该项目」（克隆/下载/阅读方式），**不得留空**（global.md §2.3）。
7. 一键脚本含 sudo 等危险操作时必须在 risks 中说明。
"""

TUTOR_CONTRACT = """
## 输出契约（严格执行，输出单个 JSON 对象，不要输出其他文字）

```json
{
  "modules": {
    "intro": "转译后的 M1 Markdown",
    "principle": "转译后的 M2 Markdown",
    "tutorial": "转译后的 M3 Markdown",
    "source-code": "转译后的 M4 Markdown",
    "deploy": "转译后的 M5 Markdown（技术事实、命令、参数、版本号一律不得改动）",
    "growth": "转译后的 M6 Markdown"
  },
  "glossary": [{"term": "术语", "explain": "一句话大白话解释"}]
}
```

硬性要求：
1. 只做语言通俗化：不修改任何技术事实、命令、参数、版本号；不改动模块结构与顺序（global.md §5.1）。
2. 专业术语首次出现处补充「术语（一句话解释，就像……）」（global.md §1.2）。
3. 保留全部【注意】风险提示，可改措辞但不得删除信息（global.md §4）。
4. 删除套话空话（global.md §1.4），每句话携带可验证信息。
5. **M5 不得出现「待补全」这类占位符**；若发现，直接补齐为具体内容（V7 判定项）。
6. **标题层级**：模块正文内部只能用 `###` 及更深层级；严禁使用 `##`（那是模块标题专用层级）。
   若上游模块正文里出现 `##`，降级为 `###` 后再输出。
"""


def analyst_system() -> str:
    return load_agent("RepoAnalystAgent") + "\n\n" + load_global() + "\n\n" + ANALYST_CONTRACT


def deploy_system() -> str:
    return load_agent("DeployAgent") + "\n\n" + load_global() + "\n\n" + DEPLOY_CONTRACT


def tutor_system() -> str:
    return load_agent("TutorAgent") + "\n\n" + load_global() + "\n\n" + TUTOR_CONTRACT


REPAIR_CONTRACT = """
## 修复任务

终审门禁检出以下问题，请逐条修复并重新输出完整 JSON（契约同上）。
只修复列出的问题与关联表述，不要推翻已达标内容；技术事实、命令、版本号仍不得改动。
"""
