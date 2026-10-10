"""GitHub-Trend-Learner CLI 入口（design.md §14）。

用法：
  python main.py daily [--top N] [--no-mail]   每日热门抓取 + 解读 + 归档/邮件
  python main.py repo <URL|owner/repo>          解析指定仓库
  python main.py collect [--pool N]             仅刷新候选池（抓取+打标+翻译，零 LLM）
  python main.py translate                      为候选池补齐中文描述（免费引擎，带缓存）
  python main.py cache [--dry-run] [--prune]    查看缓存占用；--prune 按保留期清理
  python main.py export [--date D] [--out F]    把产出文档打包成 ZIP
  python main.py serve [--at HH:MM]             常驻模式：每日定时执行 daily
  python main.py doctor                         检查配置与网络

可视化控制台：python start_ui.py（见 design.md §15）
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime, timedelta

# Windows 控制台中文输出兜底
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.stdin.reconfigure(errors="replace")
except Exception:
    pass

from app import log
from app.config import CACHE_DIR, LOGS_DIR, OUTPUTS_DIR, Settings
from app.orchestrator import Orchestrator


def cmd_daily(args) -> int:
    orch = Orchestrator()
    report = orch.run_daily(top_n=args.top, no_mail=args.no_mail)
    return 0 if report.get("ok") else 1


def cmd_repo(args) -> int:
    orch = Orchestrator()
    report = orch.run_repo(args.url)
    return 0 if report.get("ok") else 1


def cmd_collect(args) -> int:
    """仅刷新候选池：抓取热门榜单 → 规则打标 → 免费引擎翻译。

    **不调用 LLM**，因此可随时执行来扩充/更新「发现仓库」页的候选池。
    """
    from app import candidates, translate, trending
    from app.github_client import GitHubClient

    s = Settings.load()
    pool = args.pool or s.candidate_pool_size
    client = GitHubClient(token=s.github_token, max_retries=s.max_retries)
    day = f"{date.today():%Y-%m-%d}"
    log.console(f"[候选池] 开始抓取，目标 {pool} 个仓库…")

    repos, source = trending.fetch_trending(client, pool)
    if not repos:
        log.console("[候选池] 抓取失败：trending 页面与 Search API 均不可用")
        return 1
    log.console(f"[候选池] 来源 {source}，抓到 {len(repos)} 个仓库")

    if source == "trending_page":
        filled = trending.enrich_repo_metadata(client, repos, limit=pool)
        log.console(f"[候选池] 补齐元信息 {filled} 个")

    snap = candidates.build_day_snapshot(repos, source, day)
    candidates.save(day, snap)
    log.console(f"[候选池] 已写入 {snap['count']} 个候选")

    translated = translate.translate_items(snap["items"])
    if translated:
        candidates.save(day, snap)
    log.console(f"[候选池] 描述翻译：新增 {translated} 条（免费引擎，带缓存，零 LLM）")
    candidates.cleanup()
    return 0


def cmd_translate(_args) -> int:
    """为已有候选池补齐中文描述（免费翻译引擎 + 内容寻址缓存）。"""
    from app import candidates, translate

    fixed = translate.normalize_cache()
    if fixed:
        log.console(f"[翻译] 缓存后处理更新 {fixed} 条")
    added = candidates.translate_all_snapshots()
    log.console(f"[翻译] 完成：新增 {added} 条；缓存累计 {len(translate.load_cache())} 条")
    return 0


def cmd_serve(args) -> int:
    """常驻模式：每日 --at 时刻执行一次 daily（定时触发，Req1.1、design.md §14 调度方式）。"""
    at = args.at or "09:00"
    log.console(f"[serve] 常驻模式：每日 {at} 执行每日任务（Ctrl+C 退出）")
    while True:
        now = datetime.now()
        target = datetime.strptime(f"{now:%Y-%m-%d} {at}", "%Y-%m-%d %H:%M")
        if target <= now:
            target += timedelta(days=1)
        wait_s = (target - now).total_seconds()
        log.console(f"[serve] 下次执行：{target}（{int(wait_s)}s 后），Ctrl+C 可退出")
        try:
            time.sleep(max(wait_s, 1))
        except KeyboardInterrupt:
            log.console("[serve] 已退出")
            return 0
        except InterruptedError:
            continue
        try:
            Orchestrator().run_daily()
        except Exception as exc:
            log.console(f"[serve] 每日任务失败（不影响下次调度）：{exc}")


def cmd_doctor(_args) -> int:
    s = Settings.load()
    lines = [
        "配置自检（敏感值只显示是否配置，不回显内容，NFR6）：",
        f"  GitHub Token      : {'已配置' if s.github_token else '未配置（受未认证限流 60 次/小时）'}",
        f"  LLM 三要素        : {'齐备（model: ' + s.llm_model + '）' if s.llm_ready else '未配置（内容生成环节将降级）'}",
        f"  SMTP 邮件         : {'齐备' if s.smtp_ready else '未配置（每日任务将仅归档不发送）'}",
        f"  并发上限 / 重试 / 退回: {s.concurrency} / {s.max_retries} / {s.max_gate_returns}",
    ]
    import requests as _rq

    # 连通性与额度：必须带上 token 再探，否则测的是匿名额度（已耗尽时恒为 403，
    # 会让人误以为 token 没生效）。直接查 /rate_limit 比探 /zen 信息量大得多。
    headers = {"Accept": "application/vnd.github+json"}
    if s.github_token:
        headers["Authorization"] = f"Bearer {s.github_token}"
    try:
        resp = _rq.get("https://api.github.com/rate_limit", headers=headers, timeout=10)
        if resp.status_code == 200:
            res = (resp.json() or {}).get("resources") or {}
            core = res.get("core") or {}
            search = res.get("search") or {}
            auth = "已认证" if s.github_token else "匿名"
            lines.append(f"  api.github.com    : 可达（{auth}，HTTP 200）")
            lines.append(
                f"  API 额度          : core {core.get('remaining', '?')}/{core.get('limit', '?')}"
                f" ｜ search {search.get('remaining', '?')}/{search.get('limit', '?')}"
            )
            if s.github_token and core.get("limit") == 60:
                lines.append("                      ⚠ 额度仍为 60/小时，token 可能未生效")
        elif resp.status_code == 401:
            lines.append("  api.github.com    : 可达，但 token 无效（HTTP 401）")
            lines.append("                      请检查 token 是否过期或复制不完整")
        else:
            lines.append(f"  api.github.com    : 可达（HTTP {resp.status_code}）")
    except Exception as exc:
        lines.append(f"  api.github.com    : 不可达（{exc}）")
    for d in (CACHE_DIR, OUTPUTS_DIR, LOGS_DIR):
        try:
            d.mkdir(parents=True, exist_ok=True)
            lines.append(f"  {d.name:<8}: 可写（{d}）")
        except OSError as exc:
            lines.append(f"  {d.name:<8}: 不可写（{exc}）")
    log.console("\n".join(lines))
    return 0


def cmd_export(args) -> int:
    """把产出文档打包成 ZIP（CODE_REVIEW.md F6）。

    复用 `server.services.document_service.build_export_zip`，保证 CLI 与
    `/api/documents/export` 的打包结果一致（目录结构、MANIFEST、上限策略）。
    """
    from pathlib import Path

    from server.services import document_service

    data, filename, note = document_service.build_export_zip(args.date)
    if data is None:
        log.console(f"[导出] {note}")
        return 1

    out = Path(args.out) if args.out else OUTPUTS_DIR / filename
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    log.console(f"[导出] {note}（{len(data) / 1024:.1f} KB）-> {out}")
    return 0


def cmd_cache(args) -> int:
    """查看 / 清理缓存（CODE_REVIEW.md B7：cache/ 此前只增不减）。

    不带 `--prune` 只统计占用；`--prune` 按保留期删除可再生数据（建议先 `--dry-run` 预演）。
    """
    from app import maintenance

    files = sorted(CACHE_DIR.glob("*.json")) if CACHE_DIR.is_dir() else []
    total = sum(f.stat().st_size for f in files)
    log.console(f"[缓存] {CACHE_DIR}：{len(files)} 个文件，共 {total / 1024:.1f} KB")

    if not args.prune:
        for f in files[:12]:
            log.console(f"    {f.name}  {f.stat().st_size / 1024:.1f} KB")
        if len(files) > 12:
            log.console(f"    …另有 {len(files) - 12} 个文件")
        log.console("  加 --prune 可清理超期数据（建议先加 --dry-run 预演）")
        return 0

    report = maintenance.prune_cache(
        CACHE_DIR,
        repo_keep_days=args.repo_keep_days,
        trending_keep_days=args.trending_keep_days,
        dry_run=args.dry_run,
    )
    log.console("  " + maintenance.summarize(report))
    if args.dry_run:
        for name in (report["repo_removed"] + report["trending_removed"])[:10]:
            log.console(f"    将删除 {name}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="github-trend-learner",
                                     description="GitHub 热门仓库 AI 学习助手（六模块新手解读）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_daily = sub.add_parser("daily", help="每日热门抓取 + 解读 + 归档/邮件")
    p_daily.add_argument("--top", type=int, default=None, help="解析仓库数（默认 TRENDING_TOP_N=10）")
    p_daily.add_argument("--no-mail", action="store_true", help="跳过邮件投递，仅归档")
    p_daily.set_defaults(func=cmd_daily)

    p_repo = sub.add_parser("repo", help="解析指定仓库")
    p_repo.add_argument("url", help="GitHub 仓库链接或 owner/repo")
    p_repo.set_defaults(func=cmd_repo)

    p_collect = sub.add_parser("collect", help="仅刷新候选池（抓取+打标+翻译，零 LLM）")
    p_collect.add_argument("--pool", type=int, default=None, help="候选池规模（默认 CANDIDATE_POOL_SIZE）")
    p_collect.set_defaults(func=cmd_collect)

    p_translate = sub.add_parser("translate", help="为候选池补齐中文描述（免费引擎，带缓存）")
    p_translate.set_defaults(func=cmd_translate)

    p_cache = sub.add_parser("cache", help="查看缓存占用；--prune 按保留期清理")
    p_cache.add_argument("--prune", action="store_true", help="执行清理（默认只统计）")
    p_cache.add_argument("--dry-run", action="store_true", help="只预演，不实际删除")
    p_cache.add_argument("--repo-keep-days", type=int, default=90,
                         help="解析结果保留天数（默认 90）")
    p_cache.add_argument("--trending-keep-days", type=int, default=30,
                         help="榜单快照保留天数（默认 30）")
    p_cache.set_defaults(func=cmd_cache)

    p_export = sub.add_parser("export", help="把产出文档打包成 ZIP")
    p_export.add_argument("--date", default=None, help="只导出指定日期 YYYY-MM-DD")
    p_export.add_argument("--out", default=None, help="输出文件路径（默认 outputs/ 下）")
    p_export.set_defaults(func=cmd_export)

    p_serve = sub.add_parser("serve", help="常驻模式：每日定时执行")
    p_serve.add_argument("--at", default="09:00", help="每日执行时刻 HH:MM（默认 09:00）")
    p_serve.set_defaults(func=cmd_serve)

    p_doc = sub.add_parser("doctor", help="检查配置与网络")
    p_doc.set_defaults(func=cmd_doctor)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        log.console("已中断")
        return 130


if __name__ == "__main__":
    sys.exit(main())
