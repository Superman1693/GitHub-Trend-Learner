"""DeployAgent M5 组装（v1.5 缺陷回归）。

历史缺陷：deploy.py 只把一键脚本与风险提示追加到 Analyst 骨架之后，
LLM 生成的 `env_requirements`（逐项安装教程）与 `steps`（分系统分步命令）
被静默丢弃，最终文档残留「待 DeployAgent 补全」占位符，而门禁仍判 pass。

本测试锁定修复后的行为：结构化字段必须全部渲染进 M5 正文，且不含任何占位符。
"""
import re

from app.agents.deploy import build_m5
from app.quality_gate import PLACEHOLDER_PATTERNS, run_gate


def _sample() -> tuple[list[dict], dict, str, list[dict], list[str]]:
    env = [
        {
            "name": "Python",
            "version": "3.10–3.12",
            "install_guide": (
                "**怎么下载**：访问 python.org/downloads 下载安装包。\n\n"
                "**怎么安装**：Windows 双击安装并勾选 Add to PATH；"
                "macOS 执行 `brew install python@3.12`；Linux 执行 `apt install python3.12`。\n\n"
                "**怎么确认装好了**：执行 `python --version`，应该看到 `Python 3.12.x`。"
            ),
        },
        {
            "name": "Git",
            "version": "2.40+",
            "install_guide": (
                "**怎么下载**：访问 git-scm.com/downloads。\n\n"
                "**怎么安装**：按系统选择安装包，一路下一步即可。\n\n"
                "**怎么确认装好了**：执行 `git --version`，应该看到 `git version 2.4x.x`。"
            ),
        },
    ]
    steps = {
        "windows": [
            "第 1 步：打开 PowerShell（按 Win+R 输入 powershell 回车）。"
            "执行 `python --version`，应该看到版本号。",
            "第 2 步：切换目录。执行 `cd C:\\proj`，执行后应该看到提示符路径变化。",
            "第 3 步：克隆仓库。执行 `git clone https://github.com/owner/repo.git`，"
            "执行后应该看到出现 repo 文件夹。",
        ],
        "macos": [
            "第 1 步：打开终端（Command+空格 输入 terminal）。执行 `python3 --version`，"
            "应该看到版本号。",
            "第 2 步：克隆仓库。执行 `git clone https://github.com/owner/repo.git`，"
            "执行后应该看到出现 repo 文件夹。",
        ],
        "linux": [
            "第 1 步：打开终端（Ctrl+Alt+T）。执行 `python3 --version`，应该看到版本号。",
            "第 2 步：安装依赖。执行 `sudo apt install -y git`，"
            "执行后应该看到安装完成提示。",
        ],
    }
    script = "#!/usr/bin/env bash\nset -e\ngit --version\n"
    run_check = [
        {"step": "环境就绪", "expect": "python --version 输出 3.10 以上"},
        {"step": "仓库已克隆", "expect": "当前目录出现 repo 文件夹"},
        {"step": "项目可启动", "expect": "运行后看到服务监听提示"},
    ]
    risks = ["涉及 sudo 的操作请确认命令来源", "不要以管理员身份运行来源不明的脚本"]
    return env, steps, script, run_check, risks


def test_m5_renders_env_requirements_with_install_guide():
    env, steps, script, run_check, risks = _sample()
    m5 = build_m5(env, steps, script, run_check, risks)
    # 环境准备：名称、版本、安装教程三件事都要在
    assert "Python" in m5 and "3.10–3.12" in m5
    assert "怎么下载" in m5 and "怎么安装" in m5 and "怎么确认装好了" in m5
    assert "Git" in m5


def test_m5_renders_all_platform_steps():
    env, steps, script, run_check, risks = _sample()
    m5 = build_m5(env, steps, script, run_check, risks)
    for platform in ("Windows", "macOS", "Linux"):
        assert platform in m5
    # 步骤正文必须真的被渲染，而不是只有平台标题
    assert "git clone https://github.com/owner/repo.git" in m5
    assert "apt install -y git" in m5


def test_m5_renders_script_run_check_and_risks():
    env, steps, script, run_check, risks = _sample()
    m5 = build_m5(env, steps, script, run_check, risks)
    assert "git --version" in m5                      # 一键脚本
    assert "可运行性自检" in m5                        # 自检表
    assert "| 检查项 | 预期结果 | 是否通过 |" in m5
    assert "环境就绪" in m5 and "python --version 输出 3.10 以上" in m5
    assert "风险提示" in m5 and "sudo" in m5


def test_m5_has_no_placeholder():
    """核心回归：渲染结果不得含任何占位符。"""
    env, steps, script, run_check, risks = _sample()
    m5 = build_m5(env, steps, script, run_check, risks)
    for pattern in PLACEHOLDER_PATTERNS:
        assert not re.search(pattern, m5), f"M5 含占位符：{pattern}"


def test_m5_marks_unverified():
    env, steps, script, run_check, risks = _sample()
    m5 = build_m5(env, steps, script, run_check, risks)
    assert "未经实际执行验证" in m5


def test_m5_passes_v7_gate():
    """渲染出的 M5 必须能通过 V7 部署可运行性五项判定。"""
    env, steps, script, run_check, risks = _sample()
    m5 = build_m5(env, steps, script, run_check, risks)
    modules = {
        "intro": "这是一个把 RSS 源转成邮件摘要的小工具，适合想追技术资讯的新手。",
        "principle": "它的工作方式就像一位每天帮你读报纸的助理：定时抓取新内容并整理成摘要。",
        "tutorial": "### 极简版：3 分钟上手\n1. 安装\n2. 配置\n3. 运行\n\n### 完整版：分步教程\n1. 见文档",
        "source-code": "核心文件 `src/main.py` 负责程序入口，先读配置再启动抓取循环。",
        "deploy": m5,
        "growth": "学习路线：先跑起来 → 改一个配置 → 加一个小功能，可顺带学习定时任务。",
    }
    issues = [i for i in run_gate(modules) if i["check"] == "V7"]
    assert issues == [], f"V7 未通过：{issues}"


def test_m5_handles_empty_env_requirements():
    """项目无需依赖时也要给出明确说明，不能留空。"""
    m5 = build_m5([], {"windows": ["执行 `git clone <url>`，应该看到出现文件夹"],
                       "macos": ["执行 `git clone <url>`，应该看到出现文件夹"],
                       "linux": ["执行 `git clone <url>`，应该看到出现文件夹"]},
                  "", [], [])
    assert "无需额外安装依赖" in m5
    assert "未提供一键脚本" in m5
    assert "未生成自检清单" in m5
