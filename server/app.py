"""应用装配与 HTTP 服务入口。

请求分发顺序（404 修复的核心逻辑）：
    1. 命中 API 路由            -> 执行业务处理器
    2. 路径存在但方法不匹配      -> 405（而非 404，便于定位问题）
    3. /api/* 未命中            -> JSON 404（绝不被静态回退伪装成 200 HTML）
    4. 其他路径                 -> 静态资源 / SPA 回退 / 未构建引导页
"""
from __future__ import annotations

import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app import __version__ as APP_VERSION

from .config import ServerConfig
from .http import Request, Response, Router, error
from .http.static import serve_static
from .routes import register as register_routes

# 请求体上限：本地工具不需要接收大 body，防止 Content-Length 被放大导致内存耗尽（v1.8）
MAX_BODY_BYTES = 1024 * 1024  # 1 MB

# dev 模式跨域白名单：只放行本机前端开发/预览端口。
# 此前用 `*`，任意网页都能驱动本地写接口（如提交 daily 任务消耗 LLM 额度）——v1.8 收紧。
ALLOWED_DEV_ORIGINS = {
    "http://127.0.0.1:5173", "http://localhost:5173",
    "http://127.0.0.1:4173", "http://localhost:4173",
}


def build_router() -> Router:
    router = Router()
    register_routes(router)
    return router


class ApiHandler(BaseHTTPRequestHandler):
    """HTTP 请求处理器（API + 静态资源）。"""

    server_version = f"GTL/{APP_VERSION}"
    protocol_version = "HTTP/1.1"
    router: Router
    dev_mode: bool = False

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        sys.stderr.write(f"[http] {self.address_string()} {fmt % args}\n")

    # ---- 分发 ----

    def _dispatch(self) -> None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length < 0:
            length = 0
        if length > MAX_BODY_BYTES:
            # 未读取 body 就响应，HTTP/1.1 连接会错位，必须显式断开
            self.close_connection = True
            self._write(error(413, f"请求体过大（上限 {MAX_BODY_BYTES // 1024} KB）",
                              code="PAYLOAD_TOO_LARGE"))
            return
        body = self.rfile.read(length) if length else b""

        req = Request.from_raw(self.command, self.path, dict(self.headers), body)
        resp = self._route(req)
        self._write(resp)

    def _route(self, req: Request) -> Response:
        matched = self.router.match(req.method, req.path)
        if matched is not None:
            handler, params = matched
            req.path_params = params
            try:
                return handler(req)
            except ValueError as exc:
                # 参数/请求体校验失败：信息是给调用方的，可以回显
                return error(400, str(exc), code="BAD_REQUEST")
            except Exception:  # noqa: BLE001 - 服务边界需兜住全部异常
                # 不回显异常原文，避免泄露内部实现细节；详情只进服务端日志（v1.8）
                traceback.print_exc()
                return error(500, "服务内部错误，详情见服务端日志", code="INTERNAL_ERROR")

        allowed = self.router.allow_methods(req.path)
        if allowed:
            return error(
                405,
                f"该路径不支持 {req.method}，可用方法：{', '.join(sorted(allowed))}",
                code="METHOD_NOT_ALLOWED",
            )
        if req.path.startswith("/api"):
            return error(404, f"接口不存在：{req.path}", code="API_NOT_FOUND")

        return serve_static(req.path) or error(404, "资源不存在", code="NOT_FOUND")

    def _cors_origin(self) -> str | None:
        """dev 模式只放行白名单来源；非 dev 模式一律不返回 CORS 头。"""
        if not self.dev_mode:
            return None
        origin = (self.headers.get("Origin") or "").strip()
        return origin if origin in ALLOWED_DEV_ORIGINS else None

    def _write(self, resp: Response) -> None:
        self.send_response(resp.status)
        for key, value in resp.header_list():
            self.send_header(key, value)
        self.send_header("X-Content-Type-Options", "nosniff")
        origin = self._cors_origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(resp.body)

    # ---- HTTP 方法 ----

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch()

    def do_HEAD(self) -> None:  # noqa: N802
        self._dispatch()

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch()

    def do_OPTIONS(self) -> None:  # noqa: N802
        origin = self._cors_origin()
        if origin is None:
            # 非白名单来源不再无条件返回 `*`，直接拒绝预检（v1.8）
            self.send_response(403)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    # 未实现的方法也必须走统一分发，否则 BaseHTTPRequestHandler 会直接返回 501，
    # 掩盖「路径存在但方法不允许」的真实语义（应为 405）。
    def do_PUT(self) -> None:  # noqa: N802
        self._dispatch()

    def do_PATCH(self) -> None:  # noqa: N802
        self._dispatch()

    def do_DELETE(self) -> None:  # noqa: N802
        self._dispatch()


class _Server(ThreadingHTTPServer):
    """HTTP 服务。

    `allow_reuse_address` 必须按平台区分（v1.7 修复）：
    - Linux/macOS：SO_REUSEADDR 只允许绑定处于 TIME_WAIT 的端口，不会出现双监听，
      保留 True 可以让重启更快。
    - Windows：SO_REUSEADDR 语义不同，**允许两个进程同时绑定同一端口**，
      结果是多个实例静默共享端口、请求随机落到不同进程。
      实测曾出现 3 个实例同时监听 8000。故 Windows 下必须关闭。
    """

    allow_reuse_address = sys.platform != "win32"
    daemon_threads = True


def create_server(cfg: ServerConfig | None = None) -> ThreadingHTTPServer:
    cfg = cfg or ServerConfig.from_env()
    handler = type(
        "BoundApiHandler",
        (ApiHandler,),
        {"router": build_router(), "dev_mode": cfg.dev_mode},
    )
    return _Server((cfg.host, cfg.port), handler)


def _port_in_use(exc: OSError) -> bool:
    """Windows 报 10048 / 类 Unix 报 98，都表示端口被占用。"""
    return getattr(exc, "errno", None) in (48, 98) or getattr(exc, "winerror", None) == 10048


def run(cfg: ServerConfig | None = None) -> int:
    cfg = cfg or ServerConfig.from_env()
    try:
        httpd = create_server(cfg)
    except OSError as exc:
        if _port_in_use(exc):
            print(f"✗ 端口 {cfg.port} 已被占用，服务未启动。")
            print("  可能已有实例在运行。处理方式：")
            print(f"    · 直接访问 {cfg.base_url} 看看是否已在服务")
            print("    · 或换个端口：python -m server --port 8001")
            print("    · 或结束旧进程后重试")
            return 1
        raise

    print(f"GitHub-Trend-Learner 控制台已启动：{cfg.base_url}")
    print(f"  API 健康检查：{cfg.base_url}/api/health")
    if not cfg.dist_ready:
        print("  ⚠ 未检测到前端构建产物 frontend/dist/index.html")
        print("    请先执行：cd frontend && npm install && npm run build")
        print("    或直接使用：python start_ui.py（会自动构建）")
    print("  按 Ctrl+C 停止服务")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
    finally:
        httpd.server_close()
    return 0
