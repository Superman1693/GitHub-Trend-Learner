"""输出组装（templates/six-module-template.md、templates/email-template.md）。

六模块标准标题以 global.md §2.1 为唯一权威来源（contracts.MODULES_ORDER 同步自该表）。
"""
from __future__ import annotations

import re

from .contracts import MODULES_ORDER, FinalDoc, RepoMeta, project_type_label

SOURCE_LABEL = {"trending_page": "主方案 trending 页面", "search_api": "降级 Search API"}


def render_final_doc(meta: RepoMeta, final: FinalDoc) -> str:
    """按 six-module-template.md 头部 + 六模块标准标题组装完整文档。"""
    degraded_line = ""
    if meta.degraded:
        degraded_line = "> ⚠️ 因仓库体积限制，以下分析基于核心目录降级解析\n"
    header = (
        f"# {meta.full_name} 新手解读\n\n"
        f"> 仓库地址：{meta.html_url}\n"
        f"> 数据获取时间：{meta.fetched_at}\n"
        f"> 数据来源：{SOURCE_LABEL.get(meta.source, meta.source)}\n"
        f"> 项目类型：{project_type_label(final.modules.get('_project_type'))}\n"
        f"> Star：{meta.stars} ｜ 语言：{meta.language or '未知'} ｜ License：{meta.license or '未见'}\n"
        f"{degraded_line}\n"
    )
    if final.gate_result == "degraded":
        items = "；".join(
            f"{i.get('module')}（{i.get('check')}：{i.get('issue')}）"
            for i in final.rejected_items[:5]
        )
        header += f"> ⚠️ 质量终审未全部通过（降级交付）：{items}\n\n"

    parts = [header.rstrip()]
    for key, title in MODULES_ORDER:
        parts.append(f"\n## {title}\n\n{(final.modules.get(key) or '').strip()}\n")
    glossary = final.glossary or []
    if glossary:
        terms = "、".join(f"{g.get('term')}（{g.get('explain')}）" for g in glossary[:20])
        parts.append(f"\n---\n\n## 附：本次术语速查表\n\n{terms}\n")
    return "\n".join(parts)


# ---- 邮件摘要抽取（design.md §12.2：正文 Top 3 要点速览，附件放全文） ----

def _section(md: str, heading_pattern: str) -> str:
    """截取指定 ### 小节文本（到下一个 ###/## 为止）。"""
    m = re.search(heading_pattern, md)
    if not m:
        return ""
    rest = md[m.end():]
    stop = re.search(r"^###?\s", rest, re.M)
    return rest[:stop.start()].strip() if stop else rest.strip()


def extract_digest(modules: dict) -> dict:
    """从 M1/M2/M3/M5 确定性抽取邮件要点（不依赖 LLM）。"""
    intro = modules.get("intro", "")
    principle = modules.get("principle", "")
    tutorial = modules.get("tutorial", "")
    deploy = modules.get("deploy", "")

    one_liner = _section(intro, r"###\s*一句话.*")
    one_liner = one_liner.splitlines()[0].strip() if one_liner else ""

    analogy = ""
    m = re.search(r"^[^\n]*就像[^\n]*", principle, re.M)
    if m:
        analogy = m.group(0).strip()
    if len(analogy) > 100:
        analogy = analogy[:100] + "…"

    steps: list[str] = []
    quick = _section(tutorial, r"###\s*极简版.*")
    for line in quick.splitlines():
        sm = re.match(r"^\s*\d+\.\s+(.*)", line)
        if sm:
            steps.append(sm.group(1).strip())
        if len(steps) >= 3:
            break

    deploy_point = ""
    for line in deploy.splitlines():
        s = line.strip()
        if s and not s.startswith(("#", ">", "|", "-", "```")) and len(s) > 8:
            deploy_point = s
            break

    return {
        "one_liner": one_liner or "见附件完整解读",
        "analogy": analogy or "见附件原理讲解",
        "quick_steps": steps,
        "deploy_point": deploy_point or "见附件完整部署方案",
    }


def render_email_body(date_str: str, source: str, summary_text: str,
                      top_items: list[dict], rest_rows: list[dict],
                      degrade_notes: list[str]) -> str:
    """按 email-template.md 结构组装邮件正文（正文放核心，附件放全文）。"""
    lines = [
        f"# GitHub 今日热点解读 · {date_str}",
        "",
        f"> 数据获取时间：{date_str}",
        f"> 数据来源：{SOURCE_LABEL.get(source, source)}",
        f"> 今日共解读 {len(top_items) + len(rest_rows)} 个热门项目",
        "",
        "---",
        "",
        "## 今日技术热点总结",
        "",
        summary_text,
        "",
        "---",
        "",
        "## 今日精选（Top 3 要点速览）",
    ]
    for i, item in enumerate(top_items, 1):
        steps = "\n".join(f"   {n}. {s}" for n, s in enumerate(item["quick_steps"], 1)) or "   见附件教程"
        lines += [
            "",
            f"### {i}. {item['full_name']}　⭐ {item['stars']}　{item['language'] or '未知'}",
            "",
            f"> {item['one_liner']}",
            "",
            f"**它是怎么工作的**：{item['analogy']}",
            "",
            "**新手怎么用起来**：",
            steps,
            "",
            f"**部署要点**：{item['deploy_point']}",
            "",
            f"🔗 {item['html_url']}",
            "",
            "---",
        ]
    lines += ["", "## 其余热门项目（速览）", "",
              "| 项目 | 语言 | 一句话说明 |", "| --- | --- | --- |"]
    for r in rest_rows:
        desc = (r.get("description") or "").strip().replace("|", "/")[:60]
        lines.append(f"| {r['full_name']} | {r.get('language') or '未知'} | {desc or '见附件'} |")
    lines += [
        "",
        "> 其余项目的完整解读见附件；本地归档路径：`outputs/" + date_str + "/`。",
        "",
        "---",
        "",
        "📎 完整六模块解读见附件。",
    ]
    if degrade_notes:
        lines.append("")
        for note in degrade_notes:
            lines.append(note)
    return "\n".join(lines)
