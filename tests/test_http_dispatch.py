"""HTTP 分发与边界（server/app.py、routes/*）测试。

此前 server/app.py 覆盖率仅 31%，405/404 语义、请求体上限、CORS 白名单
这些边界只做过一次性手工 curl 验证，没有回归保护。

这里起一个**真实服务**（端口 0 = 由系统分配），用 http.client 发原始请求，
因此覆盖的是完整分发链路，而不是绕过 HTTP 层直接调 handler。
"""
from __future__ import annotations

import http.client
import json
import threading
import time

import pytest

from server.app import MAX_BODY_BYTES, create_server
from server.config import ServerConfig

_SERVER: dict = {}


@pytest.fixture(scope="module")
def server():
    httpd = create_server(ServerConfig(host="127.0.0.1", port=0, dev_mode=True))
    port = httpd.server_address[1]
    _SERVER["httpd"] = httpd
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.3)
    yield port
    httpd.shutdown()
    httpd.server_close()
    _SERVER.clear()


def _req(port: int, method: str, path: str, headers=None, body=b""):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request(method, path, body=body, headers=headers or {})
    resp = conn.getresponse()
    data = resp.read()
    hdrs = dict(resp.getheaders())
    conn.close()
    return resp.status, hdrs, data


# ---------------- 正常分发 ----------------

def test_health_returns_json_with_version(server):
    status, headers, body = _req(server, "GET", "/api/health")
    assert status == 200
    payload = json.loads(body)
    from app import __version__

    assert payload["version"] == __version__
    assert headers["Content-Type"].startswith("application/json")


def test_head_has_no_body_but_same_status(server):
    status, headers, body = _req(server, "HEAD", "/api/health")
    assert status == 200
    assert body == b""
    assert int(headers["Content-Length"]) > 0, "HEAD 应给出长度但不返回 body"


# ---------------- 405 vs 404 ----------------

def test_method_mismatch_returns_405_with_allowed_methods(server):
    status, _, body = _req(server, "DELETE", "/api/health")
    assert status == 405
    payload = json.loads(body)
    assert payload["error"]["code"] == "METHOD_NOT_ALLOWED"
    assert "GET" in payload["error"]["message"]


def test_unknown_api_path_returns_json_404_not_spa(server):
    """关键回归：/api/* 未命中必须如实返回 JSON 404，不能被 SPA 回退伪装成 200 HTML。"""
    status, headers, body = _req(server, "GET", "/api/definitely-not-here")
    assert status == 404
    assert headers["Content-Type"].startswith("application/json")
    assert json.loads(body)["error"]["code"] == "API_NOT_FOUND"


def test_non_api_unknown_path_falls_back_to_spa(server):
    """非 API 路径未命中应回退到前端入口，保证客户端路由刷新不 404。"""
    status, _, body = _req(server, "GET", "/some/client/route")
    assert status == 200
    assert b"<!doctype html" in body.lower() or b"<div id=" in body


# ---------------- 请求体上限 ----------------

def test_oversized_body_returns_413(server):
    status, _, body = _req(server, "POST", "/api/tasks",
                           {"Content-Length": str(MAX_BODY_BYTES + 1)})
    assert status == 413
    assert json.loads(body)["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_body_within_limit_is_accepted(server):
    payload = json.dumps({"kind": "repo", "url": "not a repo"}).encode()
    status, _, body = _req(server, "POST", "/api/tasks",
                           {"Content-Type": "application/json"}, payload)
    assert status == 400, "格式错误应是 400，说明请求体被正常读取并校验"


# ---------------- 异常处理 ----------------

def test_invalid_json_body_returns_400(server):
    status, _, body = _req(server, "POST", "/api/tasks",
                           {"Content-Type": "application/json"}, b"{not json")
    assert status == 400
    assert json.loads(body)["error"]["code"] == "INVALID_BODY"


def test_internal_error_does_not_leak_details(server, monkeypatch):
    """500 响应不得回显异常原文（可能含内部路径/密钥）。"""
    from server.app import build_router

    secret = "internal-secret-token-abc123"

    def boom(_req):
        raise RuntimeError(secret)

    router = build_router()
    router.get("/api/_boom_test", boom)
    # 注意：运行中的服务用的是 create_server 动态派生的 handler 子类，
    # 改 ApiHandler.router 不生效，必须改它自己的 RequestHandlerClass
    httpd = _SERVER["httpd"]
    httpd.RequestHandlerClass.router = router
    try:
        status, _, body = _req(server, "GET", "/api/_boom_test")
        assert status == 500
        assert secret.encode() not in body
        assert json.loads(body)["error"]["code"] == "INTERNAL_ERROR"
    finally:
        httpd.RequestHandlerClass.router = build_router()


# ---------------- CORS 与安全头 ----------------

def test_cors_echoes_allowed_dev_origin(server):
    status, headers, _ = _req(server, "GET", "/api/health", {"Origin": "http://localhost:5173"})
    assert status == 200
    assert headers.get("Access-Control-Allow-Origin") == "http://localhost:5173"
    assert headers.get("Vary") == "Origin"


def test_cors_rejects_unknown_origin(server):
    _, headers, _ = _req(server, "GET", "/api/health", {"Origin": "https://evil.example"})
    assert "Access-Control-Allow-Origin" not in headers


def test_options_preflight_forbidden_for_unknown_origin(server):
    status, headers, _ = _req(server, "OPTIONS", "/api/tasks", {"Origin": "https://evil.example"})
    assert status == 403
    assert "Access-Control-Allow-Origin" not in headers


def test_options_preflight_allowed_for_whitelisted_origin(server):
    status, headers, _ = _req(server, "OPTIONS", "/api/tasks", {"Origin": "http://127.0.0.1:5173"})
    assert status == 204
    assert headers.get("Access-Control-Allow-Origin") == "http://127.0.0.1:5173"


def test_security_header_present(server):
    _, headers, _ = _req(server, "GET", "/api/health")
    assert headers.get("X-Content-Type-Options") == "nosniff"


# ---------------- 任务接口校验 ----------------

@pytest.mark.parametrize("payload,code", [
    ({"kind": "nope"}, "INVALID_KIND"),
    ({"kind": "repo", "url": "!!!bad!!!"}, "INVALID_REPO_URL"),
    ({"kind": "daily", "top": "abc"}, "INVALID_TOP"),
    ({"kind": "daily", "top": 0}, "INVALID_TOP_RANGE"),
    ({"kind": "daily", "top": 99999}, "INVALID_TOP_RANGE"),
])
def test_task_submission_validation(server, payload, code):
    status, _, body = _req(server, "POST", "/api/tasks",
                           {"Content-Type": "application/json"},
                           json.dumps(payload).encode())
    assert status == 400
    assert json.loads(body)["error"]["code"] == code


def test_retry_unknown_task_returns_409(server):
    status, _, body = _req(server, "POST", "/api/tasks/does-not-exist/retry")
    assert status == 409
    assert json.loads(body)["error"]["code"] == "TASK_NOT_RETRYABLE"


# ---------------- 静态资源 ----------------

def test_path_traversal_does_not_serve_secrets(server):
    status, headers, body = _req(server, "GET", "/../.env")
    assert b"LLM_API_KEY" not in body
    assert b"GITHUB_TOKEN" not in body
    assert status in (200, 404)
