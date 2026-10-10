"""缓存维护：按保留期清理可再生数据（CODE_REVIEW.md B7）。

`cache/` 下的三类文件此前**只增不减**，会随使用时长线性膨胀：

| 文件 | 内容 | 清理策略 |
| --- | --- | --- |
| `repo-*.json` | 仓库解析结果（按 `head_sha` 内容寻址） | 按 mtime 超过 `repo_keep_days` 删除 |
| `trending-*.json` | 每日榜单快照（当日兜底） | 按 mtime 超过 `trending_keep_days` 删除 |
| `translations.json` | 描述译文缓存 | 超 `translation_max` 条时保留最新的（字典插入序即时间序） |

**注意**：本模块只删「可再生」数据——删掉后下次运行会重新抓取/重新翻译，
不影响任何已交付产出（`outputs/` 不在此模块职责内）。
`tasks.json`（任务历史）与 `candidates-*.json`（候选池，由 `candidates.cleanup` 负责）不在此处理。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import log

DEFAULT_REPO_KEEP_DAYS = 90
DEFAULT_TRENDING_KEEP_DAYS = 30
DEFAULT_TRANSLATION_MAX = 5000


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _age_days(path: Path) -> float:
    try:
        return (time.time() - path.stat().st_mtime) / 86400
    except OSError:
        return 0.0


def prune_cache(
    cache_dir: Path | str,
    *,
    repo_keep_days: int = DEFAULT_REPO_KEEP_DAYS,
    trending_keep_days: int = DEFAULT_TRENDING_KEEP_DAYS,
    translation_max: int = DEFAULT_TRANSLATION_MAX,
    dry_run: bool = False,
) -> dict:
    """按保留期清理缓存，返回清理报告。

    `dry_run=True` 只统计不删除，便于先确认影响范围。
    """
    root = Path(cache_dir)
    report: dict = {
        "repo_removed": [],
        "trending_removed": [],
        "translations_removed": 0,
        "bytes_freed": 0,
        "dry_run": dry_run,
    }
    if not root.is_dir():
        return report

    def _drop(path: Path, bucket: str) -> None:
        report["bytes_freed"] += _size(path)
        report[bucket].append(path.name)
        if not dry_run:
            try:
                path.unlink()
            except OSError:
                report["bytes_freed"] -= _size(path)
                report[bucket].pop()

    for path in sorted(root.glob("repo-*.json")):
        if _age_days(path) > repo_keep_days:
            _drop(path, "repo_removed")

    for path in sorted(root.glob("trending-*.json")):
        if _age_days(path) > trending_keep_days:
            _drop(path, "trending_removed")

    translations = root / "translations.json"
    if translations.is_file():
        try:
            data = json.loads(translations.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = None
        if isinstance(data, dict) and len(data) > translation_max:
            keep = list(data.items())[-translation_max:]
            removed = len(data) - len(keep)
            report["translations_removed"] = removed
            report["bytes_freed"] += _size(translations)
            if not dry_run:
                from .fsutil import atomic_write_json

                atomic_write_json(translations, dict(keep), indent=0)

    return report


def summarize(report: dict) -> str:
    """把清理报告渲染成一行控制台摘要。"""
    freed_kb = report["bytes_freed"] / 1024
    prefix = "[缓存] 预演（未删除）" if report["dry_run"] else "[缓存] 已清理"
    return (
        f"{prefix}：解析结果 {len(report['repo_removed'])} 个、"
        f"榜单快照 {len(report['trending_removed'])} 个、"
        f"译文 {report['translations_removed']} 条，"
        f"释放 {freed_kb:.1f} KB"
    )


def auto_prune(cache_dir: Path | str) -> str | None:
    """每日任务结束后的自动清理；无删除时返回 None（不产生噪声日志）。"""
    report = prune_cache(cache_dir)
    if not (report["repo_removed"] or report["trending_removed"]
            or report["translations_removed"]):
        return None
    line = summarize(report)
    log.console("  " + line)
    return line
