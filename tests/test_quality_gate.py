"""质量门禁 V1–V7（global.md §6.4）。"""
from app.quality_gate import run_gate


def _deploy_ok() -> str:
    """满足 V3/V6/V7 全部判定的 M5 正文（含安装教程、预期结果、占位符检查项）。"""
    return (
        "### ① 环境准备\n\n"
        "#### 1. Python（需要 3.10–3.12）\n\n"
        "**怎么下载**：访问 python.org/downloads 下载对应系统的安装包。\n\n"
        "**怎么安装**：Windows 双击安装并勾选 Add to PATH；"
        "macOS 执行 `brew install python@3.12`；Linux 执行 `apt install python3.12`。\n\n"
        "**怎么确认装好了**：执行 `python --version`，应该看到 `Python 3.12.x`。\n\n"
        "### ② 分系统部署步骤\n\n"
        "#### Windows\n\n1. 在项目根目录执行 `pip install -r requirements.txt`，"
        "执行后应该看到 `Successfully installed`。\n\n"
        "#### macOS\n\n1. 同上，执行位置：项目根目录，执行后应该看到 `Successfully installed`。\n\n"
        "#### Linux\n\n1. 同上，执行后应该看到 `Successfully installed`。\n\n"
        "### ③ 一键部署脚本\n\n"
        "```bash\npip install -r requirements.txt\n```\n\n"
        "**怎么用**：在项目根目录打开终端执行。\n\n"
        "### ④ 可运行性自检\n\n"
        "| 检查项 | 预期结果 | 是否通过 |\n| --- | --- | --- |\n"
        "| 依赖安装 | 无报错 | ☐ |\n\n"
        "### ⑤ ⚠️ 风险提示\n\n"
        "- 请勿以管理员身份运行来源不明的脚本\n\n"
        "> 本命令未经实际执行验证，请谨慎执行。\n"
    )


def _good_modules() -> dict:
    """六模块齐全且全部达标的样例。"""
    return {
        "intro": "它是一个把 RSS 源转成邮件摘要的小工具（一句话定位）。适合想追技术资讯、又没时间一个网站一个网站刷的新手，也适合想找个小项目练手的开发者。",
        "principle": "它的工作方式就像一位每天帮你读报纸的助理：定时抓取（就像订牛奶，到点自动送到门口）新内容，整理成摘要再投递到你的邮箱。",
        "tutorial": "### 极简版：3 分钟上手\n1. 安装\n2. 配置\n3. 运行\n\n### 完整版：分步教程\n1. 详见项目文档与示例",
        "source-code": "核心文件 `src/main.py` 负责程序入口：它先读取配置，再启动抓取循环，把结果交给渲染模块。新手能学到模块组织方式。",
        "deploy": _deploy_ok(),
        "growth": "学习路线：先跑起来 → 改一个配置 → 加一个小功能。可顺带学习定时任务、文本处理这两个实用技能，还能借它理解信息聚合类产品的工作方式。",
    }


# ---- 基线：六模块齐全应通过 ----


def test_gate_passes_on_clean_modules():
    issues = run_gate(_good_modules())
    assert issues == [], f"意外问题：{issues}"


def test_gate_passes_with_notes_preserved():
    mods = _good_modules()
    mods["deploy"] += "\n【注意】以下命令未经实际执行验证。"
    issues = run_gate(mods, upstream_notes=["【注意】命令未经验证"])
    assert issues == []


def test_module_count_is_six():
    """v1.5：模块数应为 6（删除报错大全）。"""
    from app.contracts import MODULE_KEYS

    assert len(MODULE_KEYS) == 6
    assert "errors" not in MODULE_KEYS
    assert MODULE_KEYS == ["intro", "principle", "tutorial", "source-code", "deploy", "growth"]


# ---- V1 模块完整性 ----


def test_v1_missing_module():
    mods = _good_modules()
    mods.pop("growth")
    issues = run_gate(mods)
    assert any(i["check"] == "V1" and i["module"] == "growth" for i in issues)


def test_v1_empty_module():
    mods = _good_modules()
    mods["principle"] = "太短"
    issues = run_gate(mods)
    assert any(i["check"] == "V1" and i["module"] == "principle" for i in issues)


# ---- V5 套话 ----


def test_v5_cliche_threshold():
    mods = _good_modules()
    mods["intro"] += "这个项目非常优秀，众所周知。总而言之值得学习。"
    issues = run_gate(mods)
    assert any(i["check"] == "V5" for i in issues)


def test_v5_single_cliche_passes():
    mods = _good_modules()
    mods["intro"] += "这个项目非常优秀。"  # 单模块 1 处，未达阈值 2
    issues = run_gate(mods)
    assert not any(i["check"] == "V5" for i in issues)


# ---- V7 部署可运行性（五项判定） ----


def test_v7_platform_coverage():
    """移除 macOS 的全部痕迹（含安装教程中的提及）后，V7 ① 应报缺平台。"""
    mods = _good_modules()
    mods["deploy"] = mods["deploy"].replace("macOS", "").replace("macos", "")
    issues = run_gate(mods)
    assert any(i["check"] == "V7" and "macOS" in i["issue"] for i in issues)


def test_v7_requires_install_guide():
    """环境准备只列名称与版本号 → 不合格。"""
    mods = _good_modules()
    mods["deploy"] = (
        mods["deploy"]
        .replace("**怎么下载**", "下载")
        .replace("**怎么安装**", "安装")
        .replace("**怎么确认装好了**", "确认")
    )
    issues = run_gate(mods)
    assert any(i["check"] == "V7" and "安装教程" in i["issue"] for i in issues)


def test_v7_requires_expected_result():
    """清除所有「预期结果」痕迹（含自检表头）后，V7 ③ 应报缺预期结果。"""
    mods = _good_modules()
    mods["deploy"] = (
        mods["deploy"]
        .replace("应该看到", "查看")
        .replace("预期结果", "备注")
        .replace("预期看到", "查看")
        .replace("应该出现", "出现")
        .replace("执行后查看", "执行后完成")
    )
    issues = run_gate(mods)
    assert any(i["check"] == "V7" and "预期" in i["issue"] for i in issues)


def test_v7_rejects_placeholder():
    """回归测试：骨架占位符残留必须被门禁拦住。

    历史缺陷：DeployAgent 只追加脚本、丢弃 env_requirements/steps，
    导致「待 DeployAgent 补全」「命令待补全」原样交付给用户，而门禁却判 pass。
    """
    for placeholder in (
        "### ② 分系统分步命令骨架（由 DeployAgent 补全）",
        "1. 检查 Git 是否已安装 → 命令待补全 → 预期：输出版本号",
        "| B | Git | 待补：安装教程 + 版本号 |",
        "（待 DeployAgent 填充）",
    ):
        mods = _good_modules()
        mods["deploy"] += f"\n{placeholder}\n"
        issues = run_gate(mods)
        assert any(i["check"] == "V7" and "占位符" in i["issue"] for i in issues), (
            f"占位符未被拦截：{placeholder}"
        )


def test_v7_requires_unverified_note():
    mods = _good_modules()
    mods["deploy"] = mods["deploy"].replace("本命令未经实际执行验证，请谨慎执行。", "")
    issues = run_gate(mods)
    assert any(i["check"] == "V7" and "未经实际执行验证" in i["issue"] for i in issues)


def test_v7_requires_risk_section():
    mods = _good_modules()
    mods["deploy"] = mods["deploy"].replace("### ⑤ ⚠️ 风险提示", "### ⑤ 说明")
    issues = run_gate(mods)
    assert any(i["check"] == "V7" and "风险" in i["issue"] for i in issues)


# ---- V6 前置补齐 ----


def test_v6_requires_env_and_quickstart():
    mods = _good_modules()
    mods["deploy"] = mods["deploy"].replace("### ① 环境准备", "### ① 装东西")
    mods["tutorial"] = mods["tutorial"].replace("极简版", "快速版")
    issues = run_gate(mods)
    assert any(i["check"] == "V6" for i in issues)


# ---- V2 术语解释 ----


def test_v2_ignores_substring_in_english_word():
    """回归：`re.I` 子串匹配曾让「CLI」命中「Click here to download」里的「Cli」，
    产生假阳性并误判降级交付。英文术语必须整词匹配。"""
    mods = _good_modules()
    mods["deploy"] += "\n请点「Click here to download」下载安装包。\n"
    issues = run_gate(mods)
    assert not any(i["check"] == "V2" and "CLI" in i["issue"] for i in issues)


def test_v2_ignores_terms_inside_code_blocks():
    """命令/代码块里的术语不需要解释。"""
    mods = _good_modules()
    mods["deploy"] += "\n```bash\napi --cli --docker\n```\n"
    issues = run_gate(mods)
    assert not any(i["check"] == "V2" for i in issues)


def test_v2_flags_unexplained_term_in_prose():
    """正文里首次出现的术语未解释 → 必须报 V2。"""
    mods = _good_modules()
    mods["principle"] += "\n这个项目通过 API 和外部服务通信，把结果整理后返回。\n"
    issues = run_gate(mods)
    assert any(i["check"] == "V2" and "API" in i["issue"] for i in issues)


def test_v2_accepts_explained_term():
    """术语后紧跟括号解释 → 通过。"""
    mods = _good_modules()
    mods["principle"] += "\n这个项目通过 API（一句话解释：程序之间约定好的对话接口，就像餐厅的菜单）通信。\n"
    issues = run_gate(mods)
    assert not any(i["check"] == "V2" for i in issues)


# ---- V3 命令可复现 ----


def test_v3_latest_in_command():
    mods = _good_modules()
    mods["deploy"] += "\n```bash\npip install requests  # 装最新版\n```\n"
    issues = run_gate(mods)
    assert any(i["check"] == "V3" for i in issues)


# ---- V4 真实性 ----


def test_v4_note_marker():
    mods = _good_modules()
    for k in mods:
        mods[k] = mods[k].replace("【注意】", "")
    issues = run_gate(mods, upstream_notes=["【注意】存在不确定项"])
    # 上游有不确定项但终稿无标注 → V4 报问题（风险提示被删除）
    assert any(i["check"] == "V4" for i in issues)


def test_v4_no_notes_no_issue():
    mods = _good_modules()  # 内容全确定、上游无 notes → 不要求存在【注意】
    issues = run_gate(mods, upstream_notes=[])
    assert not any(i["check"] == "V4" for i in issues)
