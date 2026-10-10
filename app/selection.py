"""核心文件筛选（design.md §5.6）与上下文裁剪（§8.3，强制规则 global.md §8.2）。

筛选规则（§5.6）：目录重要性（src/、core/、lib/）+ 文件名命中关键词
（main、index、app、engine、core）+ 被 README 提及 + 体积适中，四项加权排序取前 10，
单文件截断至 300 行。
"""
from __future__ import annotations

import os

README_LIMIT = 20_000          # README 超过 20K 字符按章节摘要（§8.3）
TREE_LIMIT = 500               # 目录树超过 500 条按目录聚合（§8.3）
MAX_CORE_FILES = 10            # 核心文件上限（§5.6、global.md §8.2）
MAX_FILE_LINES = 300           # 单文件截断行数（§5.6、global.md §8.2）

_DIR_WEIGHT = {"src": 3, "core": 3, "lib": 3, "app": 2, "pkg": 2, "internal": 2}
_NAME_KEYWORDS = ("main", "index", "app", "engine", "core")
_SKIP_EXT = {
    ".md", ".txt", ".rst", ".json", ".yml", ".yaml", ".toml", ".cfg", ".ini",
    ".lock", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".html", ".css",
    ".pdf", ".license", ".gitignore",
}
_SKIP_DIR_PARTS = {
    "test", "tests", "docs", "doc", "examples", "example", "benchmark",
    "benchmarks", "node_modules", "vendor", ".github", "assets", "static",
    "migrations", "fixtures",
}


def _score_path(path: str, readme: str) -> int:
    parts = path.split("/")
    name = parts[-1]
    ext = os.path.splitext(name)[1].lower()
    if ext in _SKIP_EXT or name.startswith("."):
        return 0
    if any(seg.lower() in _SKIP_DIR_PARTS for seg in parts[:-1]):
        return 0
    score = 0
    # ① 目录重要性
    score += max((_DIR_WEIGHT.get(seg.lower(), 0) for seg in parts[:-1]), default=0)
    # ② 文件名关键词
    stem = os.path.splitext(name)[0].lower()
    if stem in _NAME_KEYWORDS:
        score += 3
    elif any(k in stem for k in _NAME_KEYWORDS):
        score += 2
    # ③ 被 README 提及
    if path in readme or f"`{path}`" in readme:
        score += 2
    return score


def select_core_files(tree_paths: list[str], readme: str, fetch_file, max_files: int = MAX_CORE_FILES) -> tuple[list[dict], str]:
    """按 §5.6 四项加权筛选核心文件。

    fetch_file(path) -> str 由调用方注入（GitHubClient.get_file 绑定 ref）。
    返回 (files, degrade_reason)；files 为 [{path, content}]。
    """
    scored = sorted(
        ((s, p) for p in tree_paths if (s := _score_path(p, readme)) > 0),
        key=lambda t: (-t[0], t[1]),
    )
    files: list[dict] = []
    skipped_big = 0
    tries = 0
    for score, path in scored:
        if len(files) >= max_files or tries >= max_files * 3:
            break  # 尝试上限：防止候选文件连续失败时无限消耗 API 配额
        tries += 1
        try:
            content = fetch_file(path)
        except Exception:
            continue
        lines = content.splitlines()
        if len(content) > 100_000:
            skipped_big += 1
            continue  # 体积过大不属于「体积适中」（§5.6）
        if len(lines) > MAX_FILE_LINES:
            content = "\n".join(lines[:MAX_FILE_LINES]) + \
                f"\n…（已截断：原文件 {len(lines)} 行，仅保留前 {MAX_FILE_LINES} 行）"
        files.append({"path": path, "content": content})
    reason = ""
    if skipped_big:
        reason = f"{skipped_big} 个候选文件体积过大被跳过"
    return files, reason


def trim_readme(readme: str, limit: int = README_LIMIT) -> tuple[str, bool]:
    """README 超长时按章节摘要（§8.3）：保留导语段 + 各级标题与其后首段。"""
    if len(readme) <= limit:
        return readme, False
    kept: list[str] = []
    budget = limit
    heading_seen = False
    intro_done = False       # 标题前的导语段只保留首段（简介是 README 最关键信息）
    skip_until_heading = False
    for line in readme.splitlines():
        if line.startswith("#"):
            heading_seen = True
            skip_until_heading = False
            if budget <= 0:
                kept.append("…（README 超长，以下章节已按规则摘要省略）")
                break
            kept.append(line)
            budget -= len(line) + 1
            continue
        if not heading_seen:
            if intro_done:
                continue
            if line.strip():
                kept.append(line)
                budget -= len(line) + 1
            elif kept:
                intro_done = True  # 空行 = 导语段结束
            continue
        if skip_until_heading:
            continue
        if line.strip():
            kept.append(line)
            budget -= len(line) + 1
            skip_until_heading = True  # 每个标题下只保留首段
    return "\n".join(kept), True


def aggregate_tree(paths: list[str], limit: int = TREE_LIMIT) -> tuple[list[str], bool]:
    """目录树超过 500 条时按顶级目录聚合（§8.3）。"""
    if len(paths) <= limit:
        return paths, False
    from collections import Counter

    counter: Counter = Counter()
    top_files = []
    for p in paths:
        top = p.split("/", 1)[0]
        if "/" in p:
            counter[top] += 1
        else:
            top_files.append(p)
    aggregated = [f"{d}/（{n} 个文件，已聚合）" for d, n in counter.most_common()]
    return top_files + aggregated, True
