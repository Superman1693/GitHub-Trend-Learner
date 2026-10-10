"""v1.8 修复项的回归测试。

覆盖审查报告中标记为 P0/P1 的缺陷，确保不复发：
- C1  static_check 必须拿到完整 M5 正文（否则「可复现」项恒失败）
- C2  无 README 的仓库不应被误判为「不存在/私有」
- F1  产出文档的项目类型必须是中文
- D4  目录穿越守卫必须拒绝同级前缀目录
- E1  .env 行内注释解析
- C10 非法端口回落默认值
- C9  路径参数 URL 解码
"""
from __future__ import annotations

import pytest

from app import render, static_check
from app.agents.deploy import build_m5
from app.config import _parse_value
from app.contracts import MODULES_ORDER, FinalDoc, RepoMeta, project_type_label
from app.github_client import GitHubClient, RepoNotFound

# ---------------- C1：静态校验 ----------------

def _m5_fixture() -> str:
    steps = {
        "windows": ["这一步做什么 → winget install Python.Python.3.12 → 在任意终端执行 → 应看到版本号"],
        "macos": ["这一步做什么 → brew install python@3.12 → 在终端执行 → 应看到版本号"],
        "linux": ["这一步做什么 → apt-get install python3.12 → 在终端执行 → 应看到版本号"],
    }
    return build_m5(
        [{"name": "Python", "version": "3.12", "install_guide": "去 python.org 下载安装教程"}],
        steps,
        "pip install -r requirements.txt",
        [{"step": "启动", "expect": "看到监听日志"}],
        ["请勿以管理员身份运行来源不明的脚本"],
    )


def test_static_check_passes_with_real_m5():
    """回归：传入真实 M5 正文时不应再产生假的「可复现」告警。"""
    steps = {
        "windows": ["winget install Python.Python.3.12"],
        "macos": ["brew install python@3.12"],
        "linux": ["apt-get install python3.12"],
    }
    result = static_check.check(steps, "pip install -r requirements.txt",
                                ["风险提示"], _m5_fixture())
    assert result["result"] == "pass", result["issues"]
    assert result["issues"] == []


def test_static_check_flags_empty_m5():
    """反向保护：若有人再次传空串，必须能检出问题（说明该参数确实被使用）。"""
    steps = {"windows": ["a"], "macos": ["b"], "linux": ["c"]}
    result = static_check.check(steps, "echo hi", ["风险"], "")
    assert result["result"] == "warning"
    assert any(i["item"] == "可复现" for i in result["issues"])


def test_build_m5_contains_checklist_anchors():
    """M5 正文必须含校验项依赖的锚点，否则门禁会误判。"""
    m5 = _m5_fixture()
    for anchor in ("环境准备", "风险", "未经实际执行验证", "执行位置"):
        assert anchor in m5


# ---------------- C2：无 README ----------------

def test_get_readme_returns_empty_on_404(monkeypatch):
    client = GitHubClient(token=None, max_retries=1)

    def _raise(url, **kwargs):
        raise RepoNotFound(url)

    monkeypatch.setattr(client, "_get", _raise)
    assert client.get_readme("someone/no-readme") == ""


def test_get_readme_decodes_content(monkeypatch):
    import base64

    client = GitHubClient(token=None, max_retries=1)
    payload = base64.b64encode("# 标题".encode("utf-8")).decode("ascii")

    class _Resp:
        def json(self):
            return {"content": payload}

    monkeypatch.setattr(client, "_get", lambda url, **kw: _Resp())
    assert client.get_readme("a/b") == "# 标题"


# ---------------- F1：项目类型中文化 ----------------

def _meta() -> RepoMeta:
    return RepoMeta(full_name="a/b", html_url="https://github.com/a/b", description="d",
                    stars=1, forks=0, language="Python", license="MIT", topics=[],
                    default_branch="main", head_sha="x" * 40, fetched_at="2026-10-09 23:00",
                    source="search_api", readme="", tree=[], core_files=[])


def _final(project_type: str) -> FinalDoc:
    modules = {key: "内容" * 40 for key, _ in MODULES_ORDER}
    modules["_project_type"] = project_type
    return FinalDoc(task_id="t", repo_full_name="a/b", generated_at="now",
                    modules=modules, gate_result="pass", rejected_items=[], glossary=[])


@pytest.mark.parametrize("ptype", ["tool", "ai_model", "framework", "script", "template",
                                   "resource", "unknown"])
def test_render_project_type_is_chinese(ptype):
    doc = render.render_final_doc(_meta(), _final(ptype))
    line = next(ln for ln in doc.splitlines() if ln.startswith("> 项目类型："))
    value = line.split("：", 1)[1]
    assert value == project_type_label(ptype)
    assert value not in ("", ptype), f"项目类型未中文化：{value}"


def test_project_type_labels_cover_all_enum():
    from app.contracts import PROJECT_TYPES
    for t in PROJECT_TYPES:
        assert t in project_type_label.__globals__["PROJECT_TYPE_LABELS"]


def test_no_english_enum_leaks_in_labels():
    """i18n 守卫（CODE_REVIEW.md F8）。

    本项目不做完整 i18n 框架，而是「后端集中定义标签 + 经 API 下发」。
    本测试保证：任何枚举值都有中文标签且不等于原值，
    否则会以 `tool` / `yes` / `high` 这类英文原值泄漏到界面或产出文档
    （F1 就是这样漏出去的）。
    """
    from app.classify import LABELS
    from app.contracts import PROJECT_TYPE_LABELS, PROJECT_TYPES

    missing = set(PROJECT_TYPES) - set(PROJECT_TYPE_LABELS)
    assert not missing, f"项目类型缺中文标签：{sorted(missing)}"

    for dim, mapping in LABELS.items():
        for value, label in mapping.items():
            assert label, f"{dim}.{value} 标签为空"
            assert label != value, (
                f"{dim}.{value} 未提供中文标签，会以英文原值泄漏到界面"
            )


# ---------------- D4：目录穿越 ----------------

def test_static_path_guard_rejects_sibling_prefix():
    from server.config import FRONTEND_DIST
    from server.http.static import _resolve_within_dist

    root = FRONTEND_DIST.resolve()
    assert not (root.parent / (root.name + "-evil")).is_relative_to(root)
    assert _resolve_within_dist("../dist-evil/x") is None
    assert _resolve_within_dist("../../.env") is None


def test_document_path_guard():
    from server.services.document_service import _safe_path

    assert _safe_path("../../etc", "passwd.md") is None
    assert _safe_path("2026-10-09", "../secret.md") is None
    assert _safe_path("2026-10-09", "ok.txt") is None          # 非 .md
    assert _safe_path("not-a-date", "ok.md") is None


# ---------------- E1 / C10：配置解析 ----------------

@pytest.mark.parametrize("raw,expected", [
    ("10          # 注释", "10"),
    ("60     # 注释", "60"),
    ('"abc # def"', "abc # def"),
    ("'xyz'", "xyz"),
    ("ghp_token#hash", "ghp_token#hash"),   # # 前无空白，不算注释
    ("plain", "plain"),
])
def test_env_value_parsing(raw, expected):
    assert _parse_value(raw) == expected


def test_invalid_port_falls_back(monkeypatch, capsys):
    from server.config import ServerConfig

    monkeypatch.setenv("UI_PORT", "not-a-number")
    cfg = ServerConfig.from_env()
    assert cfg.port == 8000
    assert "不是合法整数" in capsys.readouterr().out


# ---------------- C9：路径参数解码 ----------------

def test_router_decodes_path_params():
    from server.http.request import Request
    from server.http.response import json_response
    from server.http.router import Router

    router = Router()
    router.get("/api/documents/{date}/{name}",
               lambda req: json_response(req.path_params))
    req = Request.from_raw("GET", "/api/documents/2026-10-09/foo%20bar%20%E4%B8%AD%E6%96%87.md",
                           {}, b"")
    matched = router.match(req.method, req.path)
    assert matched is not None
    assert matched[1]["name"] == "foo bar 中文.md"


def test_router_does_not_decode_slash_into_extra_segment():
    """%2F 只在参数级解码，不应改变路由结构。"""
    from server.http.router import Router

    router = Router()
    router.get("/api/x/{name}", lambda req: None)
    assert router.match("GET", "/api/x/a%2Fb") is not None
    assert router.match("GET", "/api/x/a/b") is None


# ---------------- A3：版本号与模块规范单一来源 ----------------

def test_health_and_config_report_single_source_version():
    """回归：/api/health 与 /api/system/config 必须返回 app.__version__ 且不报错。"""
    import json

    from app import __version__
    from server.app import build_router
    from server.http.request import Request

    router = build_router()
    for path in ("/api/health", "/api/system/config"):
        handler, _ = router.match("GET", path)
        resp = handler(Request.from_raw("GET", path, {}, b""))
        assert resp.status == 200, (path, resp.body[:200])
        payload = json.loads(resp.body)
        assert "error" not in payload, (path, payload)
        assert payload.get("version") == __version__, (path, payload)


def test_config_exposes_module_specs():
    import json

    from app.contracts import MODULE_KEYS
    from server.app import build_router
    from server.http.request import Request

    handler, _ = build_router().match("GET", "/api/system/config")
    payload = json.loads(handler(Request.from_raw("GET", "/api/system/config", {}, b"")).body)
    keys = [m["key"] for m in payload["modules"]]
    assert keys == MODULE_KEYS
    assert all("、" not in m["name"] for m in payload["modules"]), "展示用名称不应带序号"


def test_version_is_consistent_across_artifacts():
    """回归：app.__version__ / frontend/package.json / README 文档版本必须一致。

    实际发生过——补了 CHANGELOG 却忘了 bump `__version__`，导致健康检查报旧版本。
    """
    import json
    import re

    from app import __version__
    from app.config import PROJECT_ROOT

    pkg = json.loads((PROJECT_ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    assert pkg["version"] == __version__, "frontend/package.json 版本与 app.__version__ 不一致"

    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    found = re.search(r"文档版本：v?([0-9][0-9.]*)", readme)
    assert found, "README 未声明文档版本"
    assert found.group(1).rstrip(".") == __version__, (
        f"README 文档版本 {found.group(1)} 与 app.__version__ {__version__} 不一致"
    )

    changelog = (PROJECT_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{__version__}]" in changelog, "CHANGELOG 缺少当前版本的条目"


# ---------------- B1：子阶段重试 ----------------

def _bare_orchestrator():
    """构造一个不触发 __init__（避免建 client/cache）的 Orchestrator。"""
    from app.config import Settings
    from app.orchestrator import Orchestrator

    orch = Orchestrator.__new__(Orchestrator)
    orch.settings = Settings.load()
    orch.llm = None
    return orch


def test_stage_retry_honours_max_attempts(monkeypatch):
    import time as _time

    from app.contracts import TaskEnvelope

    monkeypatch.setattr(_time, "sleep", lambda *_: None)
    orch = _bare_orchestrator()
    env = TaskEnvelope(task_id="t", trace_id="t", mode="custom_repo", repo_full_name="a/b")

    calls = {"n": 0}

    def boom():
        calls["n"] += 1
        raise RuntimeError("stage failed")

    with pytest.raises(RuntimeError):
        orch._stage_retry("AgentX", env, "a/b", boom, max_attempts=2)
    assert calls["n"] == 2, "应按 max_attempts 收敛重试次数"


def test_stage_retry_returns_first_success(monkeypatch):
    import time as _time

    from app.contracts import TaskEnvelope

    monkeypatch.setattr(_time, "sleep", lambda *_: None)
    orch = _bare_orchestrator()
    env = TaskEnvelope(task_id="t", trace_id="t", mode="custom_repo", repo_full_name="a/b")

    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient")
        return "ok"

    assert orch._stage_retry("AgentX", env, "a/b", flaky, max_attempts=3) == "ok"
    assert calls["n"] == 2
