"""候选仓库收藏（v1.8.3）。

发现页会滚动出几十上百个候选，用户看到合适的仓库需要能「先攒着、回头再解析」。
此前只能当场点「深入解析」，错过就找不回来了。

存储：`cache/favorites.json`，形如
    {"a/b": {"added_at": "2026-10-10 12:30", "note": ""}}
只存 full_name 与时间，仓库元信息仍从候选池实时取，避免数据双份不一致。

**零 LLM**：纯本地读写。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .config import CACHE_DIR
from .fsutil import atomic_write_json

FILENAME = "favorites.json"


def _path() -> Path:
    return CACHE_DIR / FILENAME


def load_all() -> dict[str, dict]:
    """读取全部收藏；文件缺失或损坏时返回空字典（不抛异常）。"""
    path = _path()
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {k: v for k, v in raw.items() if isinstance(k, str)}


def names() -> set[str]:
    """已收藏的仓库名集合（供候选列表打标记）。"""
    return set(load_all())


def is_favorited(full_name: str) -> bool:
    return full_name in load_all()


def add(full_name: str, note: str = "") -> bool:
    """加入收藏；已存在则返回 False（幂等，不刷新时间）。"""
    full_name = (full_name or "").strip()
    if not full_name or "/" not in full_name:
        return False
    data = load_all()
    if full_name in data:
        return False
    data[full_name] = {
        "added_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "note": (note or "").strip(),
    }
    atomic_write_json(_path(), data, indent=1)
    return True


def remove(full_name: str) -> bool:
    """移出收藏；不存在则返回 False。"""
    data = load_all()
    if full_name not in data:
        return False
    del data[full_name]
    atomic_write_json(_path(), data, indent=1)
    return True


def toggle(full_name: str) -> bool:
    """切换收藏状态；返回操作后的状态（True = 已收藏）。"""
    if is_favorited(full_name):
        remove(full_name)
        return False
    add(full_name)
    return True


def cleanup(known: set[str]) -> list[str]:
    """移除已不在候选池中的收藏？——**不自动清理**。

    候选池只保留 7 天快照，但用户收藏的仓库可能早已不在榜上，
    自动清理会把用户的收藏悄悄删掉。此函数仅供显式调用时参考，
    默认不接入任何自动流程。
    """
    data = load_all()
    stale = [name for name in data if name not in known]
    return stale
