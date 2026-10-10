"""运行指标聚合（v1.8.3）。

此前只有 `logs/run-YYYYMMDD.jsonl` 原始事件流，想知道「成功率多少、平均耗时多久、
缓存命中几次、这周烧了多少 token」只能手工 grep。

本模块把最近 N 天的日志聚合为可直接展示的指标。**只读，不修改日志**。
同时闭环 T16（缓存命中率验证）：`cache.hit_rate` 即所需度量。

日志格式（见 `app/log.py`）：每行一个 JSON，字段
    ts / task_id / trace_id / agent / status / attempt / duration_ms
    可选：error / gate_result / tokens / mode / static_check / kb_hit / tier

**容错优先**：日志是追加写的，可能被中断截断成半行；
单行解析失败一律跳过，不能让整块指标因一行坏数据而失败。
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from .config import LOGS_DIR

DEFAULT_DAYS = 7
MAX_EVENTS = 200_000        # 防御：日志异常膨胀时不至于把内存吃满


def _log_files(days: int) -> list[Path]:
    """取最近 `days` 天的日志文件（按文件名日期倒序后截取，再按时间正序返回）。"""
    if not LOGS_DIR.is_dir():
        return []
    files = sorted(LOGS_DIR.glob("run-*.jsonl"), reverse=True)
    cutoff = date.today() - timedelta(days=days - 1)
    keep: list[Path] = []
    for path in files:
        stem = path.stem                      # run-YYYYMMDD
        raw = stem.split("-", 1)[-1]
        try:
            day = datetime.strptime(raw, "%Y%m%d").date()
        except ValueError:
            continue                          # 命名不符合约定的一律忽略
        if day >= cutoff:
            keep.append(path)
    return sorted(keep)


def _iter_events(days: int):
    """逐行产出事件字典，跳过空行与解析失败的行。"""
    count = 0
    for path in _log_files(days):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue                      # 截断的半行，跳过
            if isinstance(data, dict):
                count += 1
                if count > MAX_EVENTS:
                    return
                yield data


def _percentile(values: list[int], pct: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    idx = min(int(len(ordered) * pct), len(ordered) - 1)
    return ordered[idx]


def collect(days: int = DEFAULT_DAYS) -> dict:
    """聚合最近 `days` 天的运行指标。"""
    days = max(1, min(int(days), 90))

    agents: dict[str, dict] = defaultdict(lambda: {"calls": 0, "done": 0, "failed": 0,
                                                   "durations": []})
    tasks = {"started": 0, "failed": 0, "retry": 0}
    cache = {"hit": 0, "stored": 0}
    gate: dict[str, int] = defaultdict(int)
    tokens_total = 0
    events = 0
    slowest: list[dict] = []
    errors: list[dict] = []

    for ev in _iter_events(days):
        events += 1
        agent = str(ev.get("agent") or "unknown")
        status = str(ev.get("status") or "")

        tokens_total += int(ev.get("tokens") or 0)

        duration = ev.get("duration_ms")
        if isinstance(duration, (int, float)) and duration >= 0:
            agents[agent]["durations"].append(int(duration))
            slowest.append({
                "agent": agent,
                "duration_ms": int(duration),
                "status": status,
                "task_id": ev.get("task_id"),
                "ts": ev.get("ts"),
            })

        agents[agent]["calls"] += 1
        if status == "done":
            agents[agent]["done"] += 1
        elif status == "failed":
            agents[agent]["failed"] += 1

        if agent == "OrchestratorAgent":
            if status == "start":
                tasks["started"] += 1
            elif status == "failed":
                tasks["failed"] += 1
            elif status == "retry":
                tasks["retry"] += 1
        elif agent == "cache":
            if status == "hit":
                cache["hit"] += 1
            elif status == "stored":
                cache["stored"] += 1

        if ev.get("gate_result"):
            gate[str(ev["gate_result"])] += 1

        err = ev.get("error")
        if err:
            errors.append({
                "ts": ev.get("ts"),
                "agent": agent,
                "task_id": ev.get("task_id"),
                "error": str(err)[:300],
            })

    agent_stats = {}
    for name, data in agents.items():
        durations = data.pop("durations")
        # 成功率只在「该 Agent 会记录 done」时才有意义。
        # 反例：OrchestratorAgent 只写 start/failed、从不写 done，
        # 若按 failed/(done+failed) 算会得出 0%，而它其实 19 个任务只失败 4 个；
        # cache 的 hit/stored 也不该算成功率。这类情况返回 None（未知），
        # 原始 done/failed 计数照常给出，由前端决定怎么展示。
        rate = (round(data["done"] / (data["done"] + data["failed"]), 3)
                if data["done"] > 0 else None)
        agent_stats[name] = {
            **data,
            "success_rate": rate,
            "avg_ms": int(sum(durations) / len(durations)) if durations else 0,
            "p95_ms": _percentile(durations, 0.95),
            "duration_samples": len(durations),
        }

    lookups = cache["hit"] + cache["stored"]
    slowest.sort(key=lambda x: -x["duration_ms"])
    errors.sort(key=lambda x: str(x.get("ts") or ""), reverse=True)

    # 任务级成功率：口径为「未记 failed 即视为成功」。
    # OrchestratorAgent 每个任务写一条 start，失败时再补一条 failed，
    # 因此 成功 ≈ started - failed。注意极近期启动、仍在执行的任务会被算作成功，
    # 统计窗口越长该误差越小（默认 7 天）。
    started = tasks["started"]
    return {
        "range": {
            "days": days,
            "files": len(_log_files(days)),
            "events": events,
        },
        "tasks": {
            **tasks,
            "success_rate": round((started - tasks["failed"]) / started, 3) if started else None,
        },
        "agents": dict(sorted(agent_stats.items(), key=lambda kv: -kv[1]["calls"])),
        "cache": {
            **cache,
            "lookups": lookups,
            # 命中率 = 命中 /（命中 + 新生成）；无查询时为 None，避免显示误导性的 0%
            "hit_rate": round(cache["hit"] / lookups, 3) if lookups else None,
        },
        "gate": dict(sorted(gate.items(), key=lambda kv: -kv[1])),
        "tokens": {
            "total": tokens_total,
            "avg_per_task": int(tokens_total / started) if started else 0,
        },
        "slowest": slowest[:5],
        "recent_errors": errors[:5],
    }
