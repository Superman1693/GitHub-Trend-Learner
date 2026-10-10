"""路由表：注册路由、匹配请求路径、提取路径参数。

路径模板使用 {name} 占位，例如 /api/documents/{doc_id}。
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import unquote

from .request import Request
from .response import Response

Handler = Callable[[Request], Response]


@dataclass(frozen=True)
class Route:
    method: str
    pattern: str
    regex: re.Pattern[str]
    handler: Handler


def _compile(pattern: str) -> re.Pattern[str]:
    parts = []
    for segment in pattern.strip("/").split("/"):
        if segment.startswith("{") and segment.endswith("}"):
            parts.append(f"(?P<{segment[1:-1]}>[^/]+)")
        else:
            parts.append(re.escape(segment))
    return re.compile("^/" + "/".join(parts) + "$")


class Router:
    """极简路由表；匹配失败返回 None，由上层决定 404 策略。"""

    def __init__(self) -> None:
        self._routes: list[Route] = []

    def add(self, method: str, pattern: str, handler: Handler) -> None:
        self._routes.append(Route(method.upper(), pattern, _compile(pattern), handler))

    def get(self, pattern: str, handler: Handler) -> None:
        self.add("GET", pattern, handler)

    def post(self, pattern: str, handler: Handler) -> None:
        self.add("POST", pattern, handler)

    def match(self, method: str, path: str) -> tuple[Handler, dict[str, str]] | None:
        method = method.upper()
        for route in self._routes:
            if route.method != method:
                continue
            found = route.regex.match(path)
            if found:
                # 路径参数做 URL 解码：前端用 encodeURIComponent 发送，
                # 含空格/中文的文档名若不还原会匹配不到文件（v1.8 修复）。
                # 只在参数级别解码，避免 %2F 被还原成路径分隔符影响路由结构。
                params = {k: unquote(v) for k, v in found.groupdict().items()}
                return route.handler, params
        return None

    def allow_methods(self, path: str) -> set[str]:
        """路径存在但方法不匹配时，用于返回 405 而非 404。"""
        return {
            r.method for r in self._routes if r.regex.match(path)
        }
