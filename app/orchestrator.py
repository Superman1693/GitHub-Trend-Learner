"""OrchestratorAgent（agent/OrchestratorAgent.md）：识别 · 路由 · 调度 · 聚合 · 容错。

- 路由（Req8）：URL（含深链接截取）→ custom_repo；定时信号 → daily_trend；无法识别 → 能力说明。
  v1.5：原「报错日志 → error_fix」分支已随 Req5 删除，报错修复不在系统职责内。
- 调度：仓库维度并行（上限 3，design.md §8.1）；单仓库内部串行（design.md §4）。
- 容错：只重试失败子任务 ≤3 次（global.md §7.2）；降级交付四件套（global.md §7.3）。
- 聚合：六模块文档归档 outputs/YYYY-MM-DD/ + 邮件投递（design.md §12）。
"""
from __future__ import annotations

import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path

from .agents import analyst, collector, deploy, tutor
from .cache import Cache
from .config import CACHE_DIR, MAX_AUTO_PARSE, OUTPUTS_DIR, Settings
from .contracts import TaskEnvelope
from .github_client import GitHubClient, RepoNotFound
from . import candidates, log, mailer, render, translate, trending

HELP_TEXT = """我能听懂这些输入：
1. GitHub 仓库链接（如 https://github.com/owner/repo）—— 生成六模块新手解读；
2. 「daily」或定时信号 —— 抓取今日 GitHub 热门仓库并解读。
请换一种输入再试。"""


class Orchestrator:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.load()
        self.client = GitHubClient(token=self.settings.github_token,
                                   max_retries=self.settings.max_retries)
        self.cache = Cache(CACHE_DIR)
        self.llm = None
        if self.settings.llm_ready:
            from .llm import LLMClient
            self.llm = LLMClient(self.settings.llm_base_url, self.settings.llm_api_key,
                                 self.settings.llm_model)
        self._seq = 0
        self._seq_lock = threading.Lock()

    # ---- 基础设施 ----

    def _next_task_id(self, mode: str) -> str:
        with self._seq_lock:
            self._seq += 1
            return f"{mode}-{datetime.now():%Y%m%d%H%M%S}-{self._seq}"

    def _route(self, user_input: str) -> tuple[str, str]:
        """返回 (mode, normalized_input)（Req8）。

        v1.5：不再识别报错日志；无法识别的一律走 HELP_TEXT 引导用户提供仓库链接。
        """
        text = user_input.strip()
        if text.lower() in ("daily", "每日", "今日热门") or text == "cron":
            return "daily_trend", text
        if re.match(r"^https?://(www\.)?github\.com/", text) or re.match(r"^[\w.-]+/[\w.-]+$", text):
            return "custom_repo", text
        return "unknown", text

    def _archive(self, date_str: str, filename: str, content: str) -> Path:
        return mailer.archive(OUTPUTS_DIR, date_str, filename, content)

    def _degrade_message(self, failed_part: str, reason: str, done_part: str, next_step: str) -> str:
        """降级交付四件套（global.md §7.3）。"""
        return (f"⚠️ 降级交付\n- 失败部分：{failed_part}\n- 失败原因：{reason}\n"
                f"- 已交付部分：{done_part}\n- 建议下一步：{next_step}")

    # ---- 单仓库流水线（design.md §4 时序：串行） ----

    def _pipeline_repo(self, envelope: TaskEnvelope, source: str) -> dict:
        """采集 → 缓存命中判定 → 解析 → 部署编排 → 终审 → FinalDoc。

        重试边界（global.md §7.1「只重试失败的子任务」）：
        - 阶段 1 采集：瞬态错误由 GitHubClient 内部退避重试；404 语义性失败不重试（Req2.4）。
        - 阶段 2 内容生成：LLM 未配置是确定性失败，直接降级不重试（§7.2 禁止无脑重试）；
          瞬态失败只重试本阶段 ≤3 次，**不重新采集**（复用同一 RepoMeta，§8.1 只抓取一次）。
        """
        name = envelope.repo_full_name
        started = time.time()
        log.event(envelope.task_id, envelope.trace_id, "OrchestratorAgent", "start",
                  repo=name, mode=envelope.mode)

        # ---- 阶段 1：采集 + 缓存判定（design.md §8.2） ----
        try:
            full_name = collector.resolve_full_name(name)
            repo_info = self.client.get_repo(full_name)
            head_sha = self._head_sha(full_name, repo_info.get("default_branch") or "main")
            cached = self.cache.get(full_name, head_sha)
            if cached:
                log.console(f"  [缓存] {full_name}@{head_sha[:8]} 命中，复用既有解析结果")
                log.event(envelope.task_id, envelope.trace_id, "cache", "hit", repo=full_name)
                return {"ok": True, "finaldoc": cached["finaldoc"], "cached": True,
                        "repo": full_name, "meta": cached.get("meta") or {}}
            meta = collector.collect_from_info(self.client, repo_info, source=source,
                                               head_sha=head_sha)
            log.event(envelope.task_id, envelope.trace_id, "TrendCollectorAgent", "done",
                      duration_ms=(time.time() - started) * 1000, repo=full_name)
        except RepoNotFound:
            reason = "链接无效，或该仓库为私有/已删除（未授权状态下无法区分，Req2.4）"
            log.event(envelope.task_id, envelope.trace_id, "TrendCollectorAgent", "failed",
                      error=reason, repo=name)
            return {"ok": False, "repo": name, "error": reason}
        except Exception as exc:
            log.event(envelope.task_id, envelope.trace_id, "TrendCollectorAgent", "failed",
                      error=str(exc), repo=name)
            return {"ok": False, "repo": name, "error": str(exc)}

        # ---- 阶段 2：内容生成（LLM 环节） ----
        if self.llm is None:
            reason = "LLM 未配置，内容生成环节无法执行"
            log.event(envelope.task_id, envelope.trace_id, "OrchestratorAgent", "failed",
                      error=reason, repo=full_name)
            return {"ok": False, "repo": full_name, "error": reason}

        # 重试粒度 = **子阶段**（global.md §7.1「只重试失败的子任务」）。
        # 早期实现把 analyst → deploy → tutor 整条链包在一个重试循环里，
        # 任何一步失败都会从头重跑，最坏放大到 15 次 LLM 调用（v1.8 修复）。
        try:
            draft = self._stage_retry("RepoAnalystAgent", envelope, full_name,
                                      lambda: analyst.run(self.llm, meta))
            plan, m5_full = self._stage_retry("DeployAgent", envelope, full_name,
                                              lambda: deploy.run(self.llm, meta, draft))
            log.event(envelope.task_id, envelope.trace_id, "DeployAgent", "static_check",
                      static_check=plan.static_check.get("result"), repo=full_name)
            final = self._stage_retry(
                "TutorAgent", envelope, full_name,
                lambda: tutor.run(self.llm, meta, draft, plan, m5_full,
                                  max_returns=self.settings.max_gate_returns),
                # TutorAgent 内部已有「门禁退回 ≤max_returns 次」的循环，
                # 外层再重试 3 次会乘出 9 次调用；收紧为 2 次，仅用于兜住
                # JSON 解析失败等非瞬态错误（瞬态错误 LLMClient 内部已重试）。
                max_attempts=2)
        except Exception as exc:
            log.event(envelope.task_id, envelope.trace_id, "OrchestratorAgent", "failed",
                      error=str(exc), repo=full_name)
            return {"ok": False, "repo": full_name, "error": str(exc)}

        final.task_id = envelope.task_id
        final.modules["_project_type"] = draft.project_type
        log.event(envelope.task_id, envelope.trace_id, "TutorAgent", "done",
                  gate_result=final.gate_result, repo=full_name)
        # 仅缓存通过终审的结果：降级交付的文档质量未达标，
        # 若写进缓存会因 head_sha 未变而永久复用，再也不会重试（v1.5 修复）。
        if final.gate_result == "pass":
            self.cache.put(full_name, head_sha, final.to_dict(), final.generated_at,
                           meta=meta.to_dict())
            log.event(envelope.task_id, envelope.trace_id, "cache", "stored", repo=full_name)
        else:
            log.event(envelope.task_id, envelope.trace_id, "cache", "skipped",
                      reason="gate_result=degraded", repo=full_name)
        return {"ok": True, "finaldoc": final.to_dict(), "cached": False,
                "repo": full_name, "meta": meta.to_dict()}

    def _stage_retry(self, agent: str, envelope: TaskEnvelope, repo: str, fn,
                     max_attempts: int | None = None):
        """在**单个子阶段内**重试 ≤max_attempts 次（global.md §7.1）。

        已成功阶段的结果由调用方持有，重试不会重跑它们——这是与「整链重试」的核心区别。
        最坏 LLM 调用数 = analyst(3) + deploy(3) + tutor(2 × 内部 3 次门禁循环) = 12，
        远低于整链重试的 15 次，且典型场景（仅末阶段失败）只多花 1–2 次。
        """
        attempts = max(1, max_attempts if max_attempts is not None
                       else self.settings.max_retries)
        last_exc: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                result = fn()
                log.event(envelope.task_id, envelope.trace_id, agent, "done",
                          attempt=attempt, tokens=getattr(self.llm, "last_usage_total", 0),
                          repo=repo)
                return result
            except Exception as exc:  # noqa: BLE001 - 子阶段失败在此收敛并重试
                last_exc = exc
                log.event(envelope.task_id, envelope.trace_id, agent, "retry",
                          attempt=attempt, error=str(exc), repo=repo)
                if attempt < attempts:
                    time.sleep(min(2 ** attempt, 8))
        raise last_exc if last_exc is not None else RuntimeError(f"{agent} 未产出结果")

    def _head_sha(self, full_name: str, ref: str) -> str:
        return self.client.get_branch_sha(full_name, ref)

    # ---- 三个对外流程 ----

    def run_repo(self, url: str) -> dict:
        """Req2：粘贴链接自定义解析。"""
        task_id = self._next_task_id("custom")
        envelope = TaskEnvelope(task_id=task_id, trace_id=task_id, mode="custom_repo",
                                repo_full_name=url)
        try:
            collector.resolve_full_name(url)
        except collector.InvalidURL:
            return {"ok": False,
                    "message": "输入不是合法的 GitHub 仓库链接。正确格式示例：https://github.com/owner/repo（Req2.3）"}
        result = self._pipeline_repo(envelope, source="search_api")
        if result["ok"]:
            meta = result.get("meta")
            final = result["finaldoc"]
            doc = self._render_doc(meta, final)
            path = self._archive(datetime.now().strftime("%Y-%m-%d"),
                                 f"{result['repo'].replace('/', '_')}.md", doc)
            log.console(f"✔ 完成：{result['repo']}（门禁：{final.get('gate_result')}，缓存："
                        f"{'命中' if result.get('cached') else '未命中'}）\n  归档：{path}")
            return {"ok": True, "path": str(path), "gate_result": final.get("gate_result")}
        reason = result.get("error", "未知")
        done = "已完成链接校验与仓库数据采集" if "LLM" in reason else "无"
        next_step = ("在 .env 配置 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL 后重试"
                     if "LLM" in reason else "确认仓库为公开仓库后重试")
        msg = self._degrade_message("仓库六模块解读生成", reason, done, next_step)
        log.console(msg)
        return {"ok": False, "message": msg}

    def run_daily(self, top_n: int | None = None, no_mail: bool = False) -> dict:
        """Req1：每日热门抓取 + 六模块解读 + 邮件/归档。

        v1.8：候选池规模（`CANDIDATE_POOL_SIZE`）与「自动解析数量」（`top_n`）解耦——
        抓取并打标一个更大的池子供发现页挑选，但只对 top_n 个仓库调用 LLM 生成文档，
        既扩充了可选仓库，又不放大 token 成本。
        """
        top_n = top_n or self.settings.trending_top_n
        # 防御性钳制：调用方（CLI / API）都可能传入异常大的值，这里兜住 LLM 成本上界（v1.8）
        try:
            top_n = max(1, min(int(top_n), MAX_AUTO_PARSE))
        except (TypeError, ValueError):
            top_n = self.settings.trending_top_n
        pool_size = max(self.settings.candidate_pool_size, top_n)
        task_id = self._next_task_id("daily")
        day = date.today()
        date_str = f"{day:%Y-%m-%d}"
        log.console(f"[每日任务 {task_id}] 开始：候选池 {pool_size} / 自动解析 Top {top_n}")

        # 榜单当日快照缓存（design.md §8.2 兜底）；source 随快照保存/恢复（Req1.6）
        repos, source = None, "trending_page"
        snapshot = self.cache.get_trending(day)
        if snapshot:
            repos = snapshot["repos"]
            source = snapshot.get("source", "trending_page")
            log.console("  [缓存] 命中当日榜单快照")
        else:
            repos, source = trending.fetch_trending(self.client, pool_size)
            self.cache.put_trending(day, repos, source)
        if not repos:
            msg = self._degrade_message("热门榜单获取", "trending 页面与 Search API 均失败",
                                        "无", "稍后重试或检查网络（Req1.5/1.7）")
            log.console(msg)
            return {"ok": False, "message": msg}
        log.console(f"  [榜单] 来源 {source}，共 {len(repos)} 个仓库")

        # 补齐元信息（trending 页面不含 topics，会让规则打标大量退化为「待进一步了解」）
        # 每个仓库 1 次 /repos 调用，并发执行；失败不影响主流程。
        if source == "trending_page":
            try:
                filled = trending.enrich_repo_metadata(self.client, repos, limit=pool_size)
                if filled:
                    log.console(f"  [补齐] {filled} 个仓库的 topics/元信息已补全")
            except Exception as exc:  # noqa: BLE001 - 补齐失败不阻断
                log.console(f"  [补齐] 元信息补齐失败（不影响后续）：{exc}")

        # 候选池快照（design.md §16.3，Req10）：规则打标 + 免费引擎翻译，**零 LLM 成本**
        # 即使后续解析全部失败，候选池也应保留，供发现页筛选与挑选。
        try:
            snap = candidates.build_day_snapshot(repos, source, date_str)
            candidates.save(date_str, snap)
            try:
                translated = translate.translate_items(snap["items"])
                if translated:
                    candidates.save(date_str, snap)
                    log.console(f"  [翻译] {translated} 条仓库描述已译为中文（免费引擎，带缓存）")
            except Exception as exc:  # noqa: BLE001 - 翻译失败保留英文原文
                log.console(f"  [翻译] 跳过（保留英文原文）：{exc}")
            removed = candidates.cleanup()
            log.console(f"  [候选池] 写入 {snap['count']} 个候选（规则打标，未调用 LLM）"
                        + (f"，清理超期快照 {len(removed)} 份" if removed else ""))
        except Exception as exc:  # noqa: BLE001 - 候选池失败不应中断解析
            log.console(f"  [候选池] 写入失败（不影响后续解析）：{exc}")

        # 仅对 Top N 调用 LLM 生成六模块文档（控制成本）
        to_parse = repos[:top_n]

        # 仓库维度并行，上限 3（design.md §8.1）
        results: dict[str, dict] = {}
        with ThreadPoolExecutor(max_workers=self.settings.concurrency) as pool:
            futures = {}
            for item in to_parse:
                envelope = TaskEnvelope(
                    task_id=f"{task_id}-{item['full_name'].replace('/', '_')}",
                    trace_id=task_id, mode="daily_trend",
                    repo_full_name=item["full_name"])
                futures[pool.submit(self._pipeline_repo, envelope, source)] = item["full_name"]
            for fut in as_completed(futures):
                name = futures[fut]
                try:
                    results[name] = fut.result()
                except Exception as exc:  # 线程级异常兜底（NFR5）
                    results[name] = {"ok": False, "repo": name, "error": str(exc)}

        ok_docs = [(r["repo"], r) for r in results.values() if r.get("ok")]
        failed = [(r["repo"], r.get("error", "")) for r in results.values() if not r.get("ok")]
        log.console(f"  [结果] 成功 {len(ok_docs)}，失败 {len(failed)}")

        # 归档 + 摘要 + 邮件（design.md §12）
        degrade_notes = []
        for name, err in failed:
            degrade_notes.append(f"⚠️ 今日有仓库解析失败：{name}（原因：{err[:80]}）。其余内容不受影响。")
        if source == "search_api":
            degrade_notes.append("ℹ️ 今日热门榜单为主数据源不可用，已降级使用 Search API，"
                                 "榜单口径可能与官方 trending 略有差异。")

        summary = self._daily_summary(to_parse, ok_docs)
        top_items, rest_rows = [], []
        for item in to_parse:
            r = results.get(item["full_name"], {})
            meta = r.get("meta") or {}
            if r.get("ok"):
                digest = render.extract_digest(r["finaldoc"]["modules"])
                top_items.append({
                    "full_name": item["full_name"],
                    "stars": meta.get("stars", item.get("stars", "?")),
                    "language": meta.get("language") or item.get("language"),
                    "html_url": meta.get("html_url") or f"https://github.com/{item['full_name']}",
                    **digest,
                })
            else:
                rest_rows.append({"full_name": item["full_name"],
                                  "language": item.get("language"),
                                  "description": item.get("description")})
        top3 = top_items[:3]
        # 成功但未进 Top3 的仓库进速览表，描述用其一句话定位（email-template.md 口径）
        rest = [{"full_name": t["full_name"], "language": t["language"],
                 "description": t["one_liner"]} for t in top_items[3:]] + rest_rows

        body = render.render_email_body(date_str, source, summary, top3, rest, degrade_notes)
        self._archive(date_str, "email-body.md", body)

        mail_status = {"delivered": False, "error": "no_mail=True 指定，跳过投递"}
        if not no_mail:
            subject = f"GitHub 今日热点解读 · {date_str}"
            # 附件：各仓库完整文档合并
            full_doc = "\n\n---\n\n".join(
                self._render_doc(results[n].get("meta"), results[n]["finaldoc"])
                for n, _ in ok_docs) or "（今日无成功解读）"
            attach = self._archive(date_str, f"{date_str}-github-trend.md", full_doc)
            mail_status = mailer.send_or_archive(self.settings, subject, body, attach)

        report = {
            "ok": True, "date": date_str, "source": source,
            "success": [n for n, _ in ok_docs], "failed": failed,
            "mail": mail_status,
        }
        log.console(f"✔ 每日任务完成：成功 {len(ok_docs)} / 失败 {len(failed)}；"
                    f"邮件：{'已投递' if mail_status['delivered'] else mail_status['error'][:60]}")
        return report

    def _daily_summary(self, repos: list, ok_docs: list) -> str:
        """当日技术热点总结（Req1.3）：LLM 可用则生成，否则确定性统计。"""
        lang_count: dict[str, int] = {}
        for item in repos:
            lang = item.get("language") or "未知"
            lang_count[lang] = lang_count.get(lang, 0) + 1
        lang_str = "、".join(f"{k}（{v} 个）" for k, v in
                             sorted(lang_count.items(), key=lambda x: -x[1])[:4])
        base = f"今日热门项目集中在：{lang_str}。"
        if self.llm is not None and ok_docs:
            try:
                items = [{"name": item["full_name"], "desc": item.get("description"),
                          "lang": item.get("language")} for item in repos]
                text = self.llm.chat(
                    "你是技术趋势总结助手。用 2–4 句简体中文大白话概括今日 GitHub 热门方向与共性，"
                    "不套话，标注对新手的意义。直接输出正文。",
                    json.dumps(items, ensure_ascii=False))
                return text.strip()
            except Exception:
                pass
        return base + "详细方向解读见各仓库六模块文档（Req1.6：数据为当日榜单快照）。"

    def _render_doc(self, meta: dict | None, finaldoc: dict) -> str:
        from .contracts import FinalDoc, RepoMeta
        meta = dict(meta or {})
        meta.setdefault("full_name", finaldoc.get("repo_full_name", ""))
        meta.setdefault("html_url", f"https://github.com/{meta['full_name']}")
        meta.setdefault("fetched_at", finaldoc.get("generated_at", ""))
        meta.setdefault("source", "search_api")
        meta.setdefault("stars", "?")
        meta.setdefault("language", None)
        meta.setdefault("license", None)
        meta.setdefault("degraded", False)
        m = RepoMeta(
            full_name=meta["full_name"], html_url=meta["html_url"],
            description=meta.get("description"), stars=meta["stars"], forks=0,
            language=meta["language"], license=meta["license"], topics=[],
            default_branch="main", head_sha="", fetched_at=meta["fetched_at"],
            source=meta["source"], readme="", tree=[], core_files=[],
            degraded=meta["degraded"], degrade_reason=meta.get("degrade_reason", ""),
        )
        f = FinalDoc(
            task_id=finaldoc.get("task_id", ""), repo_full_name=meta["full_name"],
            generated_at=finaldoc.get("generated_at", ""),
            modules=finaldoc["modules"], gate_result=finaldoc.get("gate_result", "pass"),
            rejected_items=finaldoc.get("rejected_items", []),
            glossary=finaldoc.get("glossary", []),
        )
        return render.render_final_doc(m, f)

    # ---- 入口路由（Req8） ----

    def handle(self, user_input: str) -> dict:
        mode, text = self._route(user_input)
        if mode == "daily_trend":
            return self.run_daily()
        if mode == "custom_repo":
            return self.run_repo(text)
        return {"ok": False, "message": HELP_TEXT}
