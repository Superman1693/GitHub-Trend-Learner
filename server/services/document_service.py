"""文档服务：扫描 outputs/ 目录并解析解读文档的模块结构。

设计要点：
- 按 `## 标题` 动态切分章节，不写死模块数量，因此代码侧六模块/七模块口径切换期间都能正常工作。
- 已知模块标题映射为标准 key；未知标题保留为 `section-N`，前端照常渲染。
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from ..config import OUTPUTS_DIR

_H2 = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_H1 = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_DATE_DIR = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# 标题关键词 → 标准模块 key（含已废弃的 errors，兼容历史产出）
_TITLE_KEY: list[tuple[str, str]] = [
    ("项目基础大白话介绍", "intro"),
    ("零基础通俗原理讲解", "principle"),
    ("新手入门使用教程", "tutorial"),
    ("源码核心逻辑通俗分析", "source-code"),
    ("本地一键部署完整方案", "deploy"),
    ("部署与使用常见报错大全", "errors"),
    ("新手学习提升指南", "growth"),
]


@dataclass
class DocumentMeta:
    """文档列表项。"""

    doc_id: str
    date: str
    name: str
    title: str
    size: int
    modified: str
    module_count: int


def _safe_path(date: str, name: str) -> Path | None:
    """把 (date, name) 解析到 outputs 内，越界或非法返回 None。

    用 `Path.is_relative_to` 而非字符串 `startswith`：后者会把同级目录
    `outputs-evil` 误判为在 `outputs` 内（v1.8 修复）。
    """
    if not _DATE_DIR.match(date or "") or not name or "/" in name or "\\" in name:
        return None
    if not name.endswith(".md"):
        return None
    target = (OUTPUTS_DIR / date / name).resolve()
    root = OUTPUTS_DIR.resolve()
    if not target.is_relative_to(root):
        return None
    return target if target.is_file() else None


def _module_key(title: str, index: int) -> str:
    for keyword, key in _TITLE_KEY:
        if keyword in title:
            return key
    return f"section-{index}"


def _split_modules(markdown: str) -> list[dict[str, str]]:
    """按二级标题切分章节。"""
    matches = list(_H2.finditer(markdown))
    modules: list[dict[str, str]] = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        raw_title = m.group(1).strip()
        # 去掉「一、」这类序号前缀，保留纯名称
        title = re.sub(r"^[一二三四五六七八九十]+[、.．]\s*", "", raw_title)
        modules.append(
            {
                "key": _module_key(title, i),
                "title": title,
                "raw_title": raw_title,
                "content": markdown[start:end].strip(),
            }
        )
    return modules


def _head_summary(markdown: str) -> dict[str, str]:
    """提取文档头部的元信息块（`> key：value` 形式）。"""
    info: dict[str, str] = {}
    for line in markdown.splitlines()[:20]:
        stripped = line.strip()
        if not stripped.startswith(">"):
            if info:
                break
            continue
        body = stripped.lstrip(">").strip()
        for sep in ("：", ":"):
            if sep in body:
                k, _, v = body.partition(sep)
                info.setdefault(k.strip(), v.strip())
                break
    return info


def list_documents() -> list[dict]:
    """列出全部产出文档，按日期倒序、名称升序。"""
    if not OUTPUTS_DIR.is_dir():
        return []
    items: list[DocumentMeta] = []
    for day in sorted(OUTPUTS_DIR.iterdir(), reverse=True):
        if not day.is_dir() or not _DATE_DIR.match(day.name):
            continue
        for f in sorted(day.glob("*.md")):
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            h1 = _H1.search(text)
            items.append(
                DocumentMeta(
                    doc_id=f"{day.name}/{f.name}",
                    date=day.name,
                    name=f.name,
                    title=(h1.group(1).strip() if h1 else f.stem),
                    size=f.stat().st_size,
                    modified=datetime.fromtimestamp(f.stat().st_mtime).strftime(
                        "%Y-%m-%d %H:%M"
                    ),
                    module_count=len(_H2.findall(text)),
                )
            )
    return [asdict(i) for i in items]


def load_document(date: str, name: str) -> dict | None:
    """读取单份文档并解析模块；不存在返回 None。"""
    path = _safe_path(date, name)
    if path is None:
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    h1 = _H1.search(text)
    return {
        "doc_id": f"{date}/{name}",
        "date": date,
        "name": name,
        "title": h1.group(1).strip() if h1 else name,
        "meta": _head_summary(text),
        "modules": _split_modules(text),
        "markdown": text,
        "size": path.stat().st_size,
        "modified": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
    }


def _snippet(text: str, needle: str, width: int = 100) -> str:
    """截取命中处附近的片段，供前端展示「为什么命中」（v1.8）。"""
    idx = text.lower().find(needle)
    if idx < 0:
        return ""
    half = max(10, width // 2)
    start = max(0, idx - half)
    end = min(len(text), idx + len(needle) + half)
    frag = " ".join(text[start:end].split())
    return ("…" if start > 0 else "") + frag + ("…" if end < len(text) else "")


def search_documents(query: str, max_results: int = 500) -> list[dict]:
    """**全文检索**产出文档（v1.8，CODE_REVIEW.md F5）。

    此前只按文件名与标题匹配，正文里的关键词搜不到。现在同时扫描正文，
    返回命中次数与上下文片段；按「命中次数 → 日期 → 名称」排序。

    返回**全部**命中（上限 `max_results` 仅作防御），分页由调用方负责——
    否则调用方无法区分「真实命中数」与「本页条数」。outputs/ 体量很小，全量扫描足够快。
    """
    needle = (query or "").strip().lower()
    if not needle:
        return []
    hits: list[dict] = []
    for item in list_documents():
        path = OUTPUTS_DIR / item["date"] / item["name"]
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        count = text.lower().count(needle)
        in_meta = needle in item["name"].lower() or needle in item["title"].lower()
        if not count and not in_meta:
            continue
        hits.append({
            **item,
            "match_count": count,
            "snippet": _snippet(text, needle),
            "matched_in": ("正文" if count else "") + ("标题" if in_meta else ""),
        })
    hits.sort(key=lambda h: (-h["match_count"], h["date"], h["name"]))
    return hits[:max_results]


def stats() -> dict:
    """产出概览，供仪表盘使用。"""
    docs = list_documents()
    dates = sorted({d["date"] for d in docs}, reverse=True)
    return {
        "total_documents": len(docs),
        "total_dates": len(dates),
        "latest_date": dates[0] if dates else None,
        "dates": [
            {
                "date": dt,
                "count": sum(1 for d in docs if d["date"] == dt),
            }
            for dt in dates
        ],
    }
