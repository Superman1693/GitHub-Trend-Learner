"""文件写入小工具：统一原子写，避免中途崩溃留下半截文件。

JSON 缓存、归档、译文缓存都走这里，保证「要么完整写入，要么保持原样」。
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def atomic_write_text(path: Path | str, text: str) -> None:
    """原子写文本：先写同目录临时文件，再 `replace` 覆盖目标。

    同目录临时文件保证 `replace` 是同一文件系统内的原子 rename；
    `os.replace` 在 Windows 上同样保证覆盖语义。
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, target)


def atomic_write_json(path: Path | str, data: object, *, indent: int | None = None) -> None:
    """原子写 JSON（默认紧凑，中文不转义）。"""
    text = json.dumps(data, ensure_ascii=False, indent=indent)
    atomic_write_text(path, text)
