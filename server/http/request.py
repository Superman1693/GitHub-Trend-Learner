"""请求对象：封装方法、路径、查询串、头部与请求体。"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs


@dataclass
class Request:
    method: str
    path: str
    query: dict[str, list[str]] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    path_params: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_raw(cls, method: str, raw_path: str, headers: dict[str, str], body: bytes) -> "Request":
        path, _, qs = raw_path.partition("?")
        return cls(
            method=method.upper(),
            path=path.rstrip("/") or "/",
            query=parse_qs(qs, keep_blank_values=True),
            headers={k.lower(): v for k, v in headers.items()},
            body=body,
        )

    def q(self, name: str, default: str | None = None) -> str | None:
        values = self.query.get(name)
        return values[0] if values else default

    def json(self) -> dict[str, Any]:
        if not self.body:
            return {}
        try:
            data = json.loads(self.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"请求体不是合法 JSON：{exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("请求体必须是 JSON 对象")
        return data
