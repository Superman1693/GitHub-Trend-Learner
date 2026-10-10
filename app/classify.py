"""仓库维度打标（design.md §16.4，Req13）。

**规则驱动、零 LLM**：全部判定来自元数据关键词匹配，确定性、可复现、无成本。
每个维度都附 `reasons`，说明命中了哪些规则，便于用户理解与人工校正。

五个业务维度：
    highlight        亮点
    learnable        可学习之处
    deployable       是否可部署      yes / partial / no / unknown
    playfulness      可玩性          high / medium / low / unknown
    practical_tool   是否实用小工具  yes / no / unknown
"""
from __future__ import annotations

import re

from .contracts import PROJECT_TYPE_LABELS, PROJECT_TYPES  # 单一来源，见 contracts.py

# 词表集中在此处，可扩展（design.md §16.4）

# 明显「跑不起来」的仓库类型：清单 / 教程 / 资料汇总
NON_RUNNABLE = (
    "awesome", "list", "collection", "resource", "book", "tutorial", "guide",
    "cheatsheet", "roadmap", "interview", "notes", "curated", "papers", "course",
    "learning", "docs", "handbook", "free-programming",
)

# 具备可运行形态的线索
RUNNABLE = (
    "docker", "dockerfile", "deploy", "self-host", "selfhost", "server", "service",
    "api", "web", "app", "cli", "tool", "install", "binary", "framework", "library",
    "sdk", "engine", "bot", "agent", "daemon", "backend", "frontend", "runtime",
    "running", "setup", "client", "console", "extension",
)

# 依赖清单 / 容器文件：有这些基本可直接部署
DEPLOY_ARTIFACTS = (
    "requirements.txt", "pyproject.toml", "setup.py", "package.json", "go.mod",
    "cargo.toml", "pom.xml", "build.gradle", "gemfile", "composer.json",
    "dockerfile", "docker-compose.yml", "makefile", "cmakelists.txt",
)

HIGH_PLAY = (
    "game", "3d", "graphics", "visual", "interactive", "animation", "emulator",
    "simulator", "ai", "llm", "gpt", "agent", "chatbot", "image", "video", "audio",
    "music", "generator", "playground", "sandbox", "toy", "fun", "render",
)

MED_PLAY = (
    "cli", "tool", "utility", "dashboard", "editor", "monitor", "scraper",
    "automation", "plugin", "extension", "viewer", "terminal", "shell",
)

TOOL_HINTS = (
    "cli", "tool", "utility", "automation", "script", "plugin", "extension",
    "converter", "downloader", "scraper", "formatter", "lint", "checker",
    "generator", "manager", "viewer", "reader", "cleaner", "backup", "sync",
)

# 亮点：话题关键词 → 技术方向标签
HOTSPOTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("ai", "llm", "gpt", "agent", "rag", "machine-learning", "deep-learning", "transformer", "ml"), "AI / 大模型"),
    (("automation", "workflow", "ci", "cd", "pipeline"), "自动化 / 工程效率"),
    (("cli", "terminal", "shell", "command-line"), "命令行工具"),
    (("web", "frontend", "react", "vue", "next", "svelte", "css"), "前端 / Web"),
    (("backend", "api", "server", "microservice", "rest", "graphql"), "后端 / 服务端"),
    (("data", "database", "etl", "analytics", "visualization", "sql"), "数据 / 分析"),
    (("security", "pentest", "vulnerability", "crypto", "encryption"), "安全"),
    (("game", "graphics", "3d", "render", "shader"), "游戏 / 图形"),
    (("devops", "docker", "kubernetes", "cloud", "infrastructure"), "DevOps / 云原生"),
    (("tool", "utility", "productivity"), "实用工具"),
    (("education", "learning", "tutorial", "course"), "学习资源"),
    (("mobile", "android", "ios", "flutter"), "移动端"),
)

# 可学习之处：按主要语言映射
LEARN_BY_LANG: dict[str, str] = {
    "Python": "Python 工程组织、类型标注、依赖管理与测试写法",
    "JavaScript": "现代 JS 工程化、异步编程与构建工具链",
    "TypeScript": "类型系统设计、接口抽象与大型前端工程组织",
    "Go": "并发模型（goroutine / channel）、接口设计与标准库用法",
    "Rust": "所有权与借用检查、错误处理与零成本抽象",
    "Java": "面向对象设计、依赖注入与构建工具用法",
    "C++": "内存管理、模板编程与性能优化思路",
    "C": "指针与内存布局、系统调用",
    "C#": "面向对象设计、异步编程与 .NET 生态",
    "Shell": "Shell 脚本自动化与管道组合",
    "PHP": "Web 请求处理与模板渲染",
    "Ruby": "约定优于配置的设计哲学",
    "Kotlin": "空安全设计、协程与 JVM 生态互操作",
    "Swift": "现代 iOS 应用结构与内存管理",
    "HTML": "页面结构与语义化标签",
    "Jupyter Notebook": "数据分析流程与可视化表达",
    "Vue": "组件化与响应式数据流",
    "Dart": "跨平台 UI 开发与状态管理",
}

# 可学习之处：按项目类型补充
LEARN_BY_TYPE: dict[str, str] = {
    "ai_model": "模型推理流程与提示词工程",
    "framework": "框架的分层设计与扩展点",
    "tool": "命令行参数设计、配置管理与错误处理",
    "template": "项目骨架约定与工程最佳实践",
    "script": "自动化脚本的健壮性写法",
}


def _blob(name: str, description: str | None, topics: list[str]) -> str:
    return " ".join([name or "", description or "", *[t or "" for t in topics]]).lower()


def _word_pattern(word: str) -> re.Pattern[str]:
    """英文词必须整词匹配。

    与 quality_gate 的 V2 同类教训：早期用子串匹配时，
    「rest」命中了「inte**rest**ing」、「cli」命中了「**Cli**ck」，
    导致维度打标与门禁都出现假阳性。中文无词边界，按子串处理。
    """
    if word.isascii():
        return re.compile(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])")
    return re.compile(re.escape(word))


def _hits(blob: str, words: tuple[str, ...]) -> list[str]:
    return [w for w in words if _word_pattern(w).search(blob)]


def _infer_project_type(name: str, description: str, topics: list[str], blob: str) -> str:
    def hit(*words: str) -> bool:
        return any(_word_pattern(w).search(blob) for w in words)

    if hit("awesome", "list", "collection", "resource", "book", "tutorial", "roadmap"):
        return "resource"
    if hit("template", "boilerplate", "starter", "scaffold"):
        return "template"
    if hit("llm", "gpt", "diffusion", "transformer", "model", "ai"):
        return "ai_model"
    if hit("framework", "sdk", "library", "toolkit"):
        return "framework"
    if hit("cli", "script", "plugin", "extension", "utility"):
        return "tool"
    return "tool"


def classify(
    full_name: str,
    description: str | None = None,
    topics: list[str] | None = None,
    language: str | None = None,
    *,
    tree: list[str] | None = None,
) -> dict:
    """产出 5 个维度标签 + 判定理由。

    `tree` 可选：提供文件清单时，`deployable` 判定更准（能直接看到依赖清单与 Dockerfile）。
    列表页不传（省一次 API 调用），详情页传入。
    """
    topics = [t for t in (topics or []) if t]
    name = (full_name or "").split("/")[-1]
    desc = description or ""
    blob = _blob(full_name, desc, topics)
    reasons: dict[str, list[str]] = {}

    # ---- 可部署性 ----
    if tree:
        artifacts = [p for p in tree if p.rsplit("/", 1)[-1].lower() in DEPLOY_ARTIFACTS]
        # 根目录的依赖文件最有代表性，排在前面展示
        artifacts.sort(key=lambda p: (p.count("/"), p))
        if artifacts:
            deployable = "yes"
            reasons["deployable"] = [f"检测到依赖/容器文件：{', '.join(artifacts[:3])}"]
        else:
            deployable = "no"
            reasons["deployable"] = ["未检测到依赖清单或 Dockerfile，可能无需部署或为纯资源仓库"]
    else:
        non_run = _hits(blob, NON_RUNNABLE)
        run = _hits(blob, RUNNABLE)
        if non_run and not run:
            deployable, reasons["deployable"] = "no", [f"命中资料类关键词：{', '.join(non_run[:3])}"]
        elif run:
            deployable, reasons["deployable"] = "yes", [f"命中可运行关键词：{', '.join(run[:3])}"]
        else:
            deployable, reasons["deployable"] = "unknown", ["元数据未提供足够线索，查看详情可精确判定"]

    # ---- 可玩性 ----
    high = _hits(blob, HIGH_PLAY)
    med = _hits(blob, MED_PLAY)
    if high:
        playfulness, reasons["playfulness"] = "high", [f"命中趣味方向：{', '.join(high[:3])}"]
    elif med:
        playfulness, reasons["playfulness"] = "medium", [f"命中工具方向：{', '.join(med[:3])}"]
    elif deployable == "no":
        playfulness, reasons["playfulness"] = "low", ["资料/文档类项目，偏阅读而非动手"]
    else:
        playfulness, reasons["playfulness"] = "low", ["未命中趣味或工具关键词，偏底层库"]

    # ---- 实用小工具 ----
    tools = _hits(blob, TOOL_HINTS)
    if tools and deployable != "no":
        practical, reasons["practical_tool"] = "yes", [f"命中工具关键词：{', '.join(tools[:3])}"]
    elif tools:
        practical, reasons["practical_tool"] = "no", ["是资料类项目，不构成可用的工具"]
    else:
        practical, reasons["practical_tool"] = "no", ["未命中工具类关键词"]

    # ---- 亮点 ----
    directions: list[str] = []
    for keys, label in HOTSPOTS:
        matched = _hits(blob, keys)
        if matched:
            directions.append(label)
    if directions:
        highlight = "、".join(directions[:2])
        reasons["highlight"] = [f"命中技术方向：{highlight}"]
    else:
        highlight = "待进一步了解"
        reasons["highlight"] = ["元数据未命中已知方向词表"]

    # ---- 可学习之处 ----
    learn_parts: list[str] = []
    if language and language in LEARN_BY_LANG:
        learn_parts.append(LEARN_BY_LANG[language])
        reasons["learnable"] = [f"按主要语言（{language}）映射"]
    ptype = _infer_project_type(full_name, desc, topics, blob)
    if ptype in LEARN_BY_TYPE:
        learn_parts.append(LEARN_BY_TYPE[ptype])
        reasons.setdefault("learnable", []).append(f"按项目类型（{ptype}）映射")
    learnable = "；".join(learn_parts) if learn_parts else "待深入解析后给出"
    if not learn_parts:
        reasons["learnable"] = ["语言与类型均未命中映射表"]

    return {
        "highlight": highlight,
        "directions": directions,
        "learnable": learnable,
        "deployable": deployable,
        "playfulness": playfulness,
        "practical_tool": practical,
        "project_type": ptype,
        "reasons": reasons,
    }


# 前端筛选器与卡片展示用的取值定义
DIMENSIONS = {
    "deployable": {"label": "是否可部署", "values": ["yes", "partial", "no", "unknown"]},
    "playfulness": {"label": "可玩性", "values": ["high", "medium", "low", "unknown"]},
    "practical_tool": {"label": "实用小工具", "values": ["yes", "no", "unknown"]},
    "project_type": {
        "label": "项目类型",
        # 与 contracts.PROJECT_TYPES 同源，去掉仅用于兜底的 unknown
        "values": [t for t in PROJECT_TYPES if t != "unknown"],
    },
}

LABELS = {
    "deployable": {"yes": "可部署", "partial": "部分可部署", "no": "无需部署", "unknown": "未知"},
    "playfulness": {"high": "高", "medium": "中", "low": "低", "unknown": "未知"},
    "practical_tool": {"yes": "是", "no": "否", "unknown": "未知"},
    "project_type": dict(PROJECT_TYPE_LABELS),
    "trend": {"new": "今日新上榜", "rising": "持续在榜", "unknown": "未知"},
}
