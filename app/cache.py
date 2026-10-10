"""内容寻址缓存（design.md §8.2，已确认）。

- 缓存键：`full_name + head_sha`（head_sha 唯一定位一次提交）。
- 命中：仓库无新提交则直接复用既有解析结果，不重新抓取与解析。
- 失效：head_sha 变化即视为新版本；**模块口径变更亦视为失效**（见 _schema_compatible）。
- 兜底：仅「热门榜单列表本身」设当日有效（每日快照，跨日重取）。
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

from .contracts import MODULE_KEYS
from .fsutil import atomic_write_json


def repo_key(full_name: str, head_sha: str) -> str:
    raw = f"{full_name}@{head_sha}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class Cache:
    def __init__(self, cache_dir: Path) -> None:
        self.dir = Path(cache_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    # ---- 仓库解析结果（内容寻址） ----

    @staticmethod
    def _schema_compatible(payload: dict) -> bool:
        """模块口径变更后旧缓存必须失效。

        v1.5 由七模块改为六模块（删除报错大全）。缓存键只含 `full_name + head_sha`，
        不含口径版本；若不校验，仓库未更新时会继续复用七模块的旧解读结果。
        下划线开头的内部键（如 `_project_type`）不参与比对。
        """
        modules = (payload.get("finaldoc") or {}).get("modules") or {}
        keys = {k for k in modules if not k.startswith("_")}
        return keys == set(MODULE_KEYS)

    def get(self, full_name: str, head_sha: str) -> dict | None:
        path = self.dir / f"repo-{repo_key(full_name, head_sha)}.json"
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if payload.get("full_name") != full_name:
            return None
        if not self._schema_compatible(payload):
            return None
        return payload

    def put(self, full_name: str, head_sha: str, finaldoc: dict, generated_at: str,
            meta: dict | None = None) -> None:
        path = self.dir / f"repo-{repo_key(full_name, head_sha)}.json"
        payload = {
            "full_name": full_name,
            "head_sha": head_sha,
            "generated_at": generated_at,
            "finaldoc": finaldoc,
            "meta": meta or {},
        }
        atomic_write_json(path, payload, indent=1)

    # ---- 热门榜单（当日快照兜底，design.md §8.2；来源随快照保存，Req1.6） ----

    def get_trending(self, day: date) -> dict | None:
        """返回 {"source": ..., "repos": [...]}；旧格式 list 兼容为 search_api 来源。"""
        path = self.dir / f"trending-{day:%Y-%m-%d}.json"
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if isinstance(payload, list):  # 兼容修复前的旧快照格式
            return {"source": "search_api", "repos": payload}
        return payload if "repos" in payload else None

    def put_trending(self, day: date, repos: list, source: str) -> None:
        path = self.dir / f"trending-{day:%Y-%m-%d}.json"
        payload = {"source": source, "repos": repos}
        atomic_write_json(path, payload, indent=1)
