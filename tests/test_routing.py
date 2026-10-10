"""输入路由（Req8）与链接解析（含深链接截取）。"""
import pytest

from app.agents.collector import InvalidURL, resolve_full_name
from app.orchestrator import Orchestrator


@pytest.fixture(scope="module")
def orch():
    return Orchestrator()


def test_route_daily(orch):
    assert orch._route("daily")[0] == "daily_trend"
    assert orch._route("每日")[0] == "daily_trend"


def test_route_url(orch):
    mode, _ = orch._route("https://github.com/psf/requests")
    assert mode == "custom_repo"


def test_route_deep_link(orch):
    mode, _ = orch._route("https://github.com/psf/requests/tree/main/docs")
    assert mode == "custom_repo"


def test_route_error_log_is_not_fix_mode(orch):
    """v1.5：报错日志不再路由到修复流程（Req5 已删除），应落到 unknown 并给出能力说明。"""
    text = ("Traceback (most recent call last):\n"
            "  File 'main.py', line 10, in <module>\n"
            "ModuleNotFoundError: No module named 'requests'")
    mode, _ = orch._route(text)
    assert mode == "unknown"
    assert mode != "error_fix"


def test_no_fix_entrypoint(orch):
    """v1.5：Orchestrator 不再提供 run_fix 入口。"""
    assert not hasattr(orch, "run_fix")


def test_route_unknown_gives_help(orch):
    mode, _ = orch._route("你好，你是谁？")
    assert mode == "unknown"
    report = orch.handle("你好，你是谁？")
    assert "GitHub 仓库链接" in report["message"]  # Req8.5：能力说明而非报错


def test_help_text_has_no_fix_claim(orch):
    """能力说明不应再宣称提供报错修复服务。"""
    from app.orchestrator import HELP_TEXT

    assert "报错" not in HELP_TEXT
    assert "知识库" not in HELP_TEXT
    assert "六模块" in HELP_TEXT


def test_resolve_full_name():
    assert resolve_full_name("https://github.com/psf/requests") == "psf/requests"
    assert resolve_full_name("https://github.com/psf/requests/tree/main") == "psf/requests"
    assert resolve_full_name("https://github.com/psf/requests/blob/main/README.md") == "psf/requests"
    assert resolve_full_name("https://github.com/psf/requests/issues/123") == "psf/requests"
    assert resolve_full_name("psf/requests") == "psf/requests"
    with pytest.raises(InvalidURL):
        resolve_full_name("https://gitlab.com/a/b")
    with pytest.raises(InvalidURL):
        resolve_full_name("随便说点什么")


def test_invalid_url_message():
    orch = Orchestrator()
    report = orch.run_repo("not-a-url")
    assert report["ok"] is False
    assert "正确格式示例" in report["message"]  # Req2.3
