"""后端服务装配（server/app.py）。

重点覆盖 v1.7 修复的「端口重复绑定」缺陷：
Windows 下 SO_REUSEADDR 语义与 Unix 不同，会让多个实例同时绑定同一端口，
导致请求随机落到不同进程、状态不一致。实测曾出现 3 个实例同时监听 8000。
"""
import socket
import sys

import pytest

from server.app import _port_in_use, _Server, create_server
from server.config import ServerConfig


def test_allow_reuse_address_is_platform_aware():
    """Windows 必须关闭 allow_reuse_address，Unix 保留（便于快速重启）。"""
    if sys.platform == "win32":
        assert _Server.allow_reuse_address is False
    else:
        assert _Server.allow_reuse_address is True


def test_daemon_threads_enabled():
    assert _Server.daemon_threads is True


@pytest.mark.parametrize("errno_,winerror,expected", [
    (48, None, True),      # macOS / BSD: EADDRINUSE
    (98, None, True),      # Linux: EADDRINUSE
    (10048, 10048, True),  # Windows: WSAEADDRINUSE
    (13, None, False),     # EACCES 不是端口占用
    (None, None, False),
])
def test_port_in_use_detection(errno_, winerror, expected):
    exc = OSError("boom")
    exc.errno = errno_
    if winerror is not None:
        exc.winerror = winerror
    assert _port_in_use(exc) is expected


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_second_instance_on_same_port_is_rejected():
    """回归：第二个实例必须绑定失败，而不是静默共享端口。"""
    port = _free_port()
    cfg = ServerConfig(host="127.0.0.1", port=port, dev_mode=False)

    first = create_server(cfg)
    try:
        with pytest.raises(OSError) as exc_info:
            create_server(cfg)
        assert _port_in_use(exc_info.value), (
            f"第二次绑定应因端口占用失败，实际错误：{exc_info.value}"
        )
    finally:
        first.server_close()


def test_create_server_binds_and_serves():
    port = _free_port()
    httpd = create_server(ServerConfig(host="127.0.0.1", port=port, dev_mode=False))
    try:
        assert httpd.server_address[0] == "127.0.0.1"
        assert httpd.server_address[1] == port
        assert hasattr(httpd, "router") is False  # 路由挂在 handler 上，不在 server 上
    finally:
        httpd.server_close()
