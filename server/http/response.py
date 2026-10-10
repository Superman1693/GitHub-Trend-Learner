"""响应封装：统一 JSON 成功/错误结构与静态文件响应。

错误结构固定为 {"error": {"code": str, "message": str}}，前端只需处理一种形态。
"""
from __future__ import annotations

import json
import mimetypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("application/json", ".json")
mimetypes.add_type("font/woff2", ".woff2")


@dataclass
class Response:
    status: int = 200
    body: bytes = b""
    content_type: str = "application/json; charset=utf-8"
    headers: dict[str, str] = field(default_factory=dict)

    def header_list(self) -> list[tuple[str, str]]:
        return [
            ("Content-Type", self.content_type),
            ("Content-Length", str(len(self.body))),
            ("Cache-Control", self.headers.get("Cache-Control", "no-store")),
            *[(k, v) for k, v in self.headers.items() if k != "Cache-Control"],
        ]


def json_response(data: Any, status: int = 200) -> Response:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return Response(status=status, body=payload)


def error(status: int, message: str, code: str | None = None) -> Response:
    return json_response(
        {"error": {"code": code or f"HTTP_{status}", "message": message}}, status=status
    )


def text_response(text: str, status: int = 200) -> Response:
    return Response(status=status, body=text.encode("utf-8"))


def html_response(html: str, status: int = 200) -> Response:
    return Response(
        status=status,
        body=html.encode("utf-8"),
        content_type="text/html; charset=utf-8",
    )


def file_response(path: Path) -> Response:
    ctype, _ = mimetypes.guess_type(str(path))
    is_asset = path.suffix.lower() in (".js", ".css", ".woff2", ".svg", ".png", ".ico")
    return Response(
        status=200,
        body=path.read_bytes(),
        content_type=f"{ctype or 'application/octet-stream'}"
        + ("; charset=utf-8" if ctype and ctype.startswith("text/") else ""),
        headers={"Cache-Control": "public, max-age=31536000, immutable"} if is_asset else {},
    )
