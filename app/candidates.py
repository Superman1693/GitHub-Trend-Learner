"""候选池（design.md §16.3，Req10/Req11）。

每日任务在抓取榜单后写入 `cache/candidates-YYYY-MM-DD.json`；
发现页读取多日快照并合并为统一的候选列表。

**零 LLM**：本模块只做规则打标与文件读写。
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from . import classify
from .config import CACHE_DIR
from .fsutil import atomic_write_json

DEFAULT_KEEP_DAYS = 7
_PREFIX = "candidates-"


def _path(day: str) -> Path:
    return CACHE_DIR / f"{_PREFIX}{day}.json"


def build_day_snapshot(repos: list[dict], source: str, day: str) -> dict:
    """把当日榜单仓库转成候选条目（含 5 维度打标）。"""
    items: list[dict] = []
    for repo in repos:
        full_name = (repo.get("full_name") or "").strip()
        if not full_name:
            continue
        topics = repo.get("topics") or []
        dims = classify.classify(
            full_name,
            repo.get("description"),
            topics,
            repo.get("language"),
        )
        items.append({
            "full_name": full_name,
            "html_url": repo.get("html_url") or f"https://github.com/{full_name}",
            "description": (repo.get("description") or "").strip(),
            "description_zh": (repo.get("description_zh") or "").strip(),
            "language": repo.get("language"),
            "stars": repo.get("stars") or 0,
            "forks": repo.get("forks") or 0,
            "stars_today": repo.get("stars_today"),
            "topics": topics,
            "dimensions": dims,
            "first_seen": day,
            "last_seen": day,
            "days": [day],
        })
    return {
        "date": day,
        "source": source,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "count": len(items),
        "items": items,
    }


def save(day: str, snapshot: dict) -> Path:
    path = _path(day)
    atomic_write_json(path, snapshot, indent=1)
    return path


def load(day: str) -> dict | None:
    path = _path(day)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def translate_snapshot(day: str) -> int:
    """就地翻译某日快照的仓库描述并落盘；返回新增译文条数。

    走免费翻译引擎 + 内容寻址缓存（见 `app/translate.py`），**不消耗 LLM**。
    """
    snap = load(day)
    if not snap:
        return 0
    from . import translate

    items = snap.get("items") or []
    if not items:
        return 0
    before = sum(1 for it in items if it.get("description_zh"))
    translate.translate_items(items)
    after = sum(1 for it in items if it.get("description_zh"))
    save(day, snap)  # 始终落盘：专名修正等后处理也需回写
    return after - before


def translate_all_snapshots() -> int:
    """翻译所有已存在的快照，返回新增译文条数。"""
    return sum(translate_snapshot(day) for day in available_days())


def available_days() -> list[str]:
    """已有快照的日期，倒序。"""
    if not CACHE_DIR.is_dir():
        return []
    days = [
        p.stem[len(_PREFIX):]
        for p in CACHE_DIR.glob(f"{_PREFIX}*.json")
    ]
    return sorted(days, reverse=True)


def cleanup(keep_days: int = DEFAULT_KEEP_DAYS) -> list[str]:
    """清理超出保留期的快照，返回被删除的日期。"""
    removed: list[str] = []
    cutoff = date.today() - timedelta(days=keep_days)
    for day in available_days():
        try:
            d = date.fromisoformat(day)
        except ValueError:
            continue
        if d < cutoff:
            try:
                _path(day).unlink()
                removed.append(day)
            except OSError:
                pass
    return removed


def merged_items(days: list[str] | None = None) -> list[dict]:
    """合并多日快照；同一仓库保留首次/最近出现日期与最新元信息。"""
    days = days or available_days()
    pool: dict[str, dict] = {}
    for day in sorted(days):  # 由旧到新，保证 last_seen 取最新
        snap = load(day)
        if not snap:
            continue
        for item in snap.get("items") or []:
            key = item.get("full_name")
            if not key:
                continue
            existing = pool.get(key)
            if existing is None:
                pool[key] = dict(item)
                continue
            # 保留最早 first_seen，更新 last_seen 与元信息
            existing["last_seen"] = day
            existing["days"] = sorted({*existing.get("days", []), day})
            existing["stars"] = max(existing.get("stars") or 0, item.get("stars") or 0)
            for field in ("description", "description_zh", "language", "topics",
                          "html_url", "dimensions"):
                if item.get(field):
                    existing[field] = item[field]
    items = list(pool.values())
    latest = (available_days() or [""])[0]
    for it in items:
        it["days_count"] = len(it.get("days") or [])
        # 上榜态势：最近一期首次出现 = 今日新上榜，否则视为持续在榜（零成本规则判定）
        it["trend"] = "new" if it.get("first_seen") == latest else "rising"
    items.sort(key=lambda x: (x.get("days_count", 0), x.get("stars") or 0), reverse=True)
    return items


def facets(items: list[dict]) -> dict:
    """筛选项与分布计数（Req11.3）。"""
    languages: dict[str, int] = {}
    for it in items:
        lang = it.get("language") or "未标注"
        languages[lang] = languages.get(lang, 0) + 1

    def dist(key: str) -> dict[str, int]:
        out: dict[str, int] = {}
        for it in items:
            val = (it.get("dimensions") or {}).get(key) or "unknown"
            out[val] = out.get(val, 0) + 1
        return out

    # 技术方向：一个仓库可能命中多个方向，按「方向」逐个计数
    directions: dict[str, int] = {}
    for it in items:
        for d in (it.get("dimensions") or {}).get("directions") or []:
            directions[d] = directions.get(d, 0) + 1

    trend: dict[str, int] = {}
    for it in items:
        val = it.get("trend") or "unknown"
        trend[val] = trend.get(val, 0) + 1

    stars = [it.get("stars") or 0 for it in items]
    return {
        "total": len(items),
        "languages": dict(sorted(languages.items(), key=lambda kv: -kv[1])),
        "deployable": dist("deployable"),
        "playfulness": dist("playfulness"),
        "practical_tool": dist("practical_tool"),
        "project_type": dist("project_type"),
        "directions": dict(sorted(directions.items(), key=lambda kv: -kv[1])),
        "trend": trend,
        "stars": {
            "max": max(stars) if stars else 0,
            "min": min(stars) if stars else 0,
        },
        "days": available_days(),
    }


def apply_filters(
    items: list[dict],
    *,
    language: str | None = None,
    deployable: str | None = None,
    playfulness: str | None = None,
    practical_tool: str | None = None,
    project_type: str | None = None,
    direction: str | None = None,
    trend: str | None = None,
    min_stars: int | None = None,
    min_days: int | None = None,
    q: str | None = None,
    day: str | None = None,
) -> list[dict]:
    """多条件组合筛选（Req11.2，v1.8 扩展项目类型 / 技术方向 / 上榜态势）。"""
    out = items
    if day:
        out = [it for it in out if day in (it.get("days") or [])]
    if language:
        out = [it for it in out if (it.get("language") or "未标注") == language]
    if deployable:
        out = [it for it in out if (it.get("dimensions") or {}).get("deployable") == deployable]
    if playfulness:
        out = [it for it in out if (it.get("dimensions") or {}).get("playfulness") == playfulness]
    if practical_tool:
        out = [it for it in out if (it.get("dimensions") or {}).get("practical_tool") == practical_tool]
    if project_type:
        out = [it for it in out if (it.get("dimensions") or {}).get("project_type") == project_type]
    if direction:
        out = [it for it in out
               if direction in ((it.get("dimensions") or {}).get("directions") or [])]
    if trend:
        out = [it for it in out if (it.get("trend") or "unknown") == trend]
    if min_stars:
        out = [it for it in out if (it.get("stars") or 0) >= min_stars]
    if min_days:
        out = [it for it in out if (it.get("days_count") or 0) >= min_days]
    if q:
        needle = q.strip().lower()
        out = [
            it for it in out
            if needle in (it.get("full_name") or "").lower()
            or needle in (it.get("description") or "").lower()
            or needle in (it.get("description_zh") or "").lower()
            or any(needle in t.lower() for t in (it.get("topics") or []))
        ]
    return out


def get_item(full_name: str) -> dict | None:
    for it in merged_items():
        if it.get("full_name") == full_name:
            return it
    return None
