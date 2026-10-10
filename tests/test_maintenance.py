"""缓存维护（app/maintenance.py）测试。

覆盖 CODE_REVIEW.md B7：cache/ 下的可再生数据必须能按保留期清理，
且不得误删任务历史与候选池快照。
"""
from __future__ import annotations

import json
import os
import time

from app import maintenance


def _make(path, content="{}", age_days=0.0):
    path.write_text(content, encoding="utf-8")
    if age_days:
        ts = time.time() - age_days * 86400
        os.utime(path, (ts, ts))
    return path


def test_prune_removes_only_expired_repo_cache(tmp_path):
    _make(tmp_path / "repo-old.json", age_days=120)
    _make(tmp_path / "repo-fresh.json", age_days=1)
    _make(tmp_path / "trending-old.json", age_days=60)
    _make(tmp_path / "trending-fresh.json", age_days=1)

    report = maintenance.prune_cache(tmp_path, repo_keep_days=90, trending_keep_days=30)

    assert report["repo_removed"] == ["repo-old.json"]
    assert report["trending_removed"] == ["trending-old.json"]
    assert not (tmp_path / "repo-old.json").exists()
    assert not (tmp_path / "trending-old.json").exists()
    assert (tmp_path / "repo-fresh.json").exists()
    assert (tmp_path / "trending-fresh.json").exists()
    assert report["bytes_freed"] > 0


def test_prune_dry_run_keeps_files(tmp_path):
    _make(tmp_path / "repo-old.json", age_days=200)
    report = maintenance.prune_cache(tmp_path, repo_keep_days=90, dry_run=True)

    assert report["dry_run"] is True
    assert report["repo_removed"] == ["repo-old.json"]
    assert (tmp_path / "repo-old.json").exists(), "预演模式不得真正删除"
    assert "预演" in maintenance.summarize(report)


def test_prune_never_touches_tasks_and_candidates(tmp_path):
    _make(tmp_path / "tasks.json", age_days=999)
    _make(tmp_path / "candidates-2020-01-01.json", age_days=999)
    _make(tmp_path / "translations.json", json.dumps({"a": "b"}), age_days=999)

    maintenance.prune_cache(tmp_path)

    assert (tmp_path / "tasks.json").exists(), "任务历史不属于缓存，不得删除"
    assert (tmp_path / "candidates-2020-01-01.json").exists(), "候选池由 candidates.cleanup 负责"
    assert (tmp_path / "translations.json").exists()


def test_translations_capped_keeping_newest(tmp_path):
    data = {f"k{i}": f"v{i}" for i in range(20)}
    _make(tmp_path / "translations.json", json.dumps(data))

    report = maintenance.prune_cache(tmp_path, translation_max=5)

    assert report["translations_removed"] == 15
    kept = json.loads((tmp_path / "translations.json").read_text(encoding="utf-8"))
    assert len(kept) == 5
    assert list(kept) == [f"k{i}" for i in range(15, 20)], "应保留最新的 5 条"


def test_translations_under_limit_untouched(tmp_path):
    _make(tmp_path / "translations.json", json.dumps({"a": "b"}))
    report = maintenance.prune_cache(tmp_path, translation_max=100)
    assert report["translations_removed"] == 0
    assert json.loads((tmp_path / "translations.json").read_text(encoding="utf-8")) == {"a": "b"}


def test_corrupt_translations_does_not_raise(tmp_path):
    _make(tmp_path / "translations.json", "{ 不是合法 JSON")
    report = maintenance.prune_cache(tmp_path, translation_max=1)
    assert report["translations_removed"] == 0


def test_missing_cache_dir_is_noop(tmp_path):
    report = maintenance.prune_cache(tmp_path / "nope")
    assert report["repo_removed"] == [] and report["bytes_freed"] == 0


def test_auto_prune_returns_none_when_nothing_removed(tmp_path):
    _make(tmp_path / "repo-fresh.json", age_days=1)
    assert maintenance.auto_prune(tmp_path) is None
