"""静态命令校验（design.md §10，无沙箱替代方案）。

五项校验：命令格式 / 平台适配 / 危险操作 / 依赖版本 / 可复现。
结果写入 DeployPlan.static_check，并统一标注「本命令未经实际执行验证」（Req4.4）。
"""
from __future__ import annotations

import re

# 占位符：<owner>、<YOUR_TOKEN>、<代理端口> 等；排除重定向 < in.txt（< 后紧跟空格）
PLACEHOLDER = re.compile(r"<[^<>\s][^<>\n]{0,29}>")
DANGER_PATTERNS = (
    "rm -rf", "sudo ", "sudo\t", "chmod 777", "mkfs", "dd if=",
    "del /f", "rd /s", "format ", "ufw ", "iptables", "netsh advfirewall",
    "firewall-cmd", "杀端口", "kill -9",
)
# 平台专属命令（用于交叉检查）
WIN_ONLY = ("winget", "choco ", "choco.exe", "powershell", "setx ", "taskkill", "netsh")
MAC_ONLY = ("brew ", "brew\t", "open -a", "softwareupdate", "launchctl")
LINUX_ONLY = ("apt-get", "apt ", "dnf ", "yum ", "pacman ", "zypper ")


def _issues_add(issues: list[dict], item: str, detail: str) -> None:
    issues.append({"item": item, "detail": detail})


UNVERIFIED_NOTE = "> 校验状态：本命令已通过静态校验，但**未经实际执行验证**，请谨慎执行。"


def check(steps: dict[str, list[str]], one_click_script: str,
          risks: list[str], m5_markdown: str) -> dict:
    """对部署内容执行五项静态校验（design.md §10 表格）。"""
    issues: list[dict] = []
    win_text = "\n".join(steps.get("windows", []))
    mac_text = "\n".join(steps.get("macos", []))
    linux_text = "\n".join(steps.get("linux", []))
    all_text = "\n".join([win_text, mac_text, linux_text, one_click_script])

    # ① 命令格式：占位符未替换、脚本为空
    for m in PLACEHOLDER.findall(one_click_script)[:5]:
        _issues_add(issues, "命令格式", f"一键脚本含未替换占位符：{m}（执行前需替换为实际值）")
    if "```" in one_click_script or "```" in all_text:
        _issues_add(issues, "命令格式", "命令文本中残留 markdown 围栏符号")
    if not one_click_script.strip():
        _issues_add(issues, "命令格式", "一键部署脚本为空")

    # ② 平台适配：跨平台命令误用（如 apt 用于 Windows）
    for cmd in LINUX_ONLY:
        if cmd in win_text:
            _issues_add(issues, "平台适配", f"Windows 步骤出现 Linux 命令：{cmd.strip()}")
    for cmd in MAC_ONLY:
        if cmd in linux_text or cmd in win_text:
            _issues_add(issues, "平台适配", f"非 macOS 步骤出现 macOS 命令：{cmd.strip()}")
    for cmd in WIN_ONLY:
        if cmd in linux_text:
            _issues_add(issues, "平台适配", f"Linux 步骤出现 Windows 命令：{cmd.strip()}")
    for cmd in LINUX_ONLY:
        if cmd in mac_text and "apt" in cmd:
            _issues_add(issues, "平台适配", f"macOS 步骤出现 Linux 命令：{cmd.strip()}")

    # ③ 危险操作：命中关键词时必须有对应风险提示
    danger_hits = [p.strip() for p in DANGER_PATTERNS if p in all_text]
    if danger_hits and not risks:
        _issues_add(issues, "危险操作", f"检测到危险操作 {danger_hits[:3]} 但 risks 为空，必须补充风险提示")

    # ④ 依赖版本：禁止「安装最新版」类不可复现表述（global.md §3.3）
    if re.search(r"最新版|latest(?![_\w])", all_text, re.I):
        _issues_add(issues, "依赖版本", "出现「最新版 / latest」表述，必须给出明确版本或版本范围")

    # ⑤ 可复现：M5 正文需含执行位置与预期结果说明
    if not re.search(r"执行位置|在哪个目录|执行后|预期", m5_markdown):
        _issues_add(issues, "可复现", "部署说明缺少执行位置或预期结果描述")

    result = "warning" if issues else "pass"
    return {
        "verified_by": "static_check（代码静态校验，无沙箱）",
        "result": result,
        "unverified_reason": "所有命令均未经实际执行验证，请谨慎执行" if issues else "",
        "issues": issues,
    }

