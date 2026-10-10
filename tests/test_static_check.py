"""静态命令校验五项（design.md §10）。"""
from app.static_check import check


def _base(**kw):
    steps = kw.pop("steps", {"windows": ["1. winget install Python.Python.3.12"],
                             "macos": ["1. brew install python@3.12"],
                             "linux": ["1. sudo apt install python3.12"]})
    one_click = kw.pop("one_click", "pip install -r requirements.txt\npython main.py")
    risks = kw.pop("risks", ["Linux 步骤使用 sudo，需要管理员密码"])
    m5 = kw.pop("m5", "### 环境准备\n执行位置：项目根目录。\n预期输出：依赖安装完成。")
    return check(steps, one_click, risks, m5)


def test_pass_on_clean_content():
    result = _base()
    assert result["result"] == "pass"
    assert result["issues"] == []
    assert "未经实际执行验证" in result["unverified_reason"] or result["unverified_reason"] == ""


def test_platform_misuse_detected():
    result = _base(steps={"windows": ["1. sudo apt install python3"],
                          "macos": ["1. brew install python"],
                          "linux": ["1. apt install python3"]})
    assert any(i["item"] == "平台适配" for i in result["issues"])


def test_latest_version_forbidden():
    result = _base(one_click="pip install requests  # 安装最新版")
    assert any(i["item"] == "依赖版本" for i in result["issues"])


def test_danger_requires_risk_note():
    result = _base(one_click="rm -rf node_modules && npm install", risks=[])
    assert any(i["item"] == "危险操作" for i in result["issues"])


def test_placeholder_detected():
    result = _base(one_click="git clone https://github.com/<owner>/<repo>.git")
    assert any(i["item"] == "命令格式" for i in result["issues"])


def test_shell_redirect_not_flagged_as_placeholder():
    result = _base(one_click="python build.py < input.txt > output.txt")
    assert not any(i["item"] == "命令格式" for i in result["issues"])


def test_reproducibility_requires_location_and_expectation():
    result = _base(m5="### 步骤\n1. 运行脚本")
    assert any(i["item"] == "可复现" for i in result["issues"])
