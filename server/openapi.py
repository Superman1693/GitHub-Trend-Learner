"""接口文档生成（CODE_REVIEW.md F11：此前无任何接口清单）。

设计取舍：本项目路由是手写的，没有装饰器式的 schema 声明，
因此**不引入重型框架**，而是：

1. 从 `Router` **内省**出真实存在的路径与方法 —— 保证「文档里有的，代码里一定有」，
   不会出现文档与实现脱节；
2. 用下方 `SUMMARIES` 表补充中文说明、查询参数与响应要点（人工维护，缺失时不报错）；
3. 由 `build_openapi()` 产出 OpenAPI 3.1 文档，`build_markdown()` 产出人读的 `API.md`。

两者都只依赖路由表与静态描述，不执行任何业务逻辑。
"""
from __future__ import annotations

from app import __version__

# 路径模板 → 说明。key 必须与 Router 中注册的 pattern 完全一致。
SUMMARIES: dict[tuple[str, str], dict] = {
    ("GET", "/api/health"): {
        "summary": "健康检查",
        "desc": "返回服务状态、版本号与前端构建产物信息。",
    },
    ("GET", "/api/system/config"): {
        "summary": "运行配置",
        "desc": "返回并发数、重试次数、LLM/SMTP/GitHub 是否就绪、六模块规范。敏感值只报告是否配置。",
    },
    ("GET", "/api/system/overview"): {
        "summary": "产出概览",
        "desc": "返回文档统计与任务运行数，供仪表盘使用。",
    },
    ("GET", "/api/openapi.json"): {
        "summary": "接口清单（OpenAPI 3.1）",
        "desc": "从路由表内省生成的机器可读接口文档，路径与方法保证与实现一致。",
    },
    ("GET", "/api/documents"): {
        "summary": "文档列表 / 全文检索",
        "desc": "不带 q 时按日期倒序返回文档列表；带 q 时执行全文检索，"
                "返回 match_count 与 snippet，total 为真实命中数。",
        "params": [("q", "关键词（触发全文检索）"), ("date", "按日期筛选 YYYY-MM-DD"),
                   ("limit", "检索模式下的分页大小，默认 50，上限 200")],
    },
    ("GET", "/api/documents/stats"): {
        "summary": "文档统计",
        "desc": "返回文档总数、日期数与每日份数分布。",
    },
    ("GET", "/api/documents/export"): {
        "summary": "批量导出 ZIP",
        "desc": "把产出文档打包为 ZIP（保留 日期/文件名.md 结构 + MANIFEST.txt）。"
                "上限 300 份 / 64 MB，超限截断并在清单注明。",
        "params": [("date", "只导出指定日期 YYYY-MM-DD；不传则导出全部")],
        "produces": "application/zip",
    },
    ("GET", "/api/documents/{date}/{name}"): {
        "summary": "文档详情",
        "desc": "返回单个文档的元信息、按 ## 切分的模块结构与完整 Markdown。",
    },
    ("GET", "/api/tasks"): {
        "summary": "任务列表",
        "desc": "按创建时间倒序返回最近的任务记录（含状态与日志）。",
        "params": [("limit", "返回条数，默认 20，上限 50")],
    },
    ("GET", "/api/tasks/{task_id}"): {
        "summary": "任务详情",
        "desc": "返回单个任务的状态、报告与实时日志。",
    },
    ("POST", "/api/tasks"): {
        "summary": "提交任务",
        "desc": "提交仓库解析（kind=repo）或每日热门（kind=daily）任务。"
                "同一目标在途时会幂等返回既有任务。",
        "body": {"kind": "repo | daily（必填）", "url": "kind=repo 时的仓库地址",
                 "top": f"kind=daily 时的解析数量，1–{50}"},
    },
    ("POST", "/api/tasks/{task_id}/retry"): {
        "summary": "重试任务",
        "desc": "以失败任务的原目标重新提交，返回新任务（retried_from 指向原任务）。",
    },
    ("GET", "/api/candidates"): {
        "summary": "候选仓库列表",
        "desc": "多条件组合筛选候选池。全部筛选为规则判定，不调用 LLM。",
        "params": [("language", "编程语言"), ("deployable", "可部署性"),
                   ("playfulness", "可玩性"), ("practical_tool", "是否实用工具"),
                   ("project_type", "项目类型"), ("direction", "技术方向"),
                   ("trend", "上榜态势 new/rising"), ("min_stars", "最低 star"),
                   ("min_days", "最少上榜天数"), ("q", "关键词"), ("day", "仅看某日上榜"),
                   ("limit", "返回条数，默认 120，上限 400")],
    },
    ("GET", "/api/candidates/facets"): {
        "summary": "候选筛选项与分布",
        "desc": "返回各维度的取值分布、star 区间、可用日期与中文标签表，供筛选器渲染。",
    },
    ("GET", "/api/candidates/{owner}/{repo}"): {
        "summary": "候选仓库详情",
        "desc": "返回单仓库的元信息、目录树与规则打标结果。",
    },
    ("POST", "/api/candidates/{owner}/{repo}/preview"): {
        "summary": "阶段一：搜索引擎摘要",
        "desc": "只调搜索引擎做轻量检索，**不调用 LLM**；返回结果明确标注「非 AI 生成」。",
        "body": {"query": "可选，自定义检索词"},
    },
    ("POST", "/api/candidates/{owner}/{repo}/analyze"): {
        "summary": "阶段二：调用 AI 深入解析",
        "desc": "提交完整六模块解析任务（**会调用 LLM**），返回任务记录。",
    },
}


def _path_params(pattern: str) -> list[str]:
    return [seg[1:-1] for seg in pattern.strip("/").split("/")
            if seg.startswith("{") and seg.endswith("}")]


def build_openapi(routes: list[tuple[str, str]]) -> dict:
    """由路由表 + SUMMARIES 生成 OpenAPI 3.1 文档。"""
    paths: dict[str, dict] = {}
    for method, pattern in routes:
        meta = SUMMARIES.get((method, pattern), {})
        operation: dict = {
            "summary": meta.get("summary", pattern),
            "description": meta.get("desc", ""),
            "operationId": f"{method.lower()}{pattern.replace('/', '_').replace('{', '').replace('}', '')}",
            "responses": {
                "200": {"description": "成功"},
                "400": {"description": "入参校验失败"},
                "404": {"description": "资源不存在"},
                "500": {"description": "服务内部错误"},
            },
        }
        params = [
            {"name": name, "in": "path", "required": True, "schema": {"type": "string"}}
            for name in _path_params(pattern)
        ]
        params += [
            {"name": name, "in": "query", "required": False, "schema": {"type": "string"},
             "description": desc}
            for name, desc in meta.get("params", [])
        ]
        if params:
            operation["parameters"] = params
        if "body" in meta:
            operation["requestBody"] = {
                "required": True,
                "content": {"application/json": {
                    "schema": {"type": "object",
                               "properties": {k: {"type": "string", "description": v}
                                              for k, v in meta["body"].items()}}}},
            }
        if "produces" in meta:
            operation["responses"]["200"]["content"] = {
                meta["produces"]: {"schema": {"type": "string", "format": "binary"}}
            }
        paths.setdefault(pattern, {})[method.lower()] = operation

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "GitHub-Trend-Learner 控制台 API",
            "version": __version__,
            "description": "由 `server/openapi.py` 从路由表内省生成，"
                           "路径与方法保证与实现一致。",
        },
        "servers": [{"url": "http://127.0.0.1:8000", "description": "本地控制台"}],
        "paths": dict(sorted(paths.items())),
    }


def build_markdown(routes: list[tuple[str, str]]) -> str:
    """生成人读的 `API.md`。"""
    lines = [
        "# 控制台 API 清单",
        "",
        f"- 版本：v{__version__}",
        "- 本文件由 `python main.py api-doc` 从路由表内省生成，请勿手工编辑。",
        f"- 共 {len(routes)} 个接口；机器可读版本见 `GET /api/openapi.json`。",
        "- 统一错误结构：`{\"error\": {\"code\": \"...\", \"message\": \"...\"}}`",
        "",
        "## 接口一览",
        "",
        "| 方法 | 路径 | 说明 |",
        "| --- | --- | --- |",
    ]
    for method, pattern in sorted(routes, key=lambda r: (r[1], r[0])):
        meta = SUMMARIES.get((method, pattern), {})
        lines.append(f"| {method} | `{pattern}` | {meta.get('summary', '—')} |")

    lines += ["", "## 接口详情", ""]
    for method, pattern in sorted(routes, key=lambda r: (r[1], r[0])):
        meta = SUMMARIES.get((method, pattern), {})
        lines += [f"### `{method} {pattern}`", "", meta.get("summary", "—"), ""]
        if meta.get("desc"):
            lines += [meta["desc"], ""]
        if meta.get("params"):
            lines += ["| 参数 | 位置 | 说明 |", "| --- | --- | --- |"]
            for name, desc in meta["params"]:
                lines.append(f"| `{name}` | query | {desc} |")
            lines.append("")
        for name in _path_params(pattern):
            lines += [f"- 路径参数：`{name}`", ""]
        if meta.get("body"):
            lines += ["请求体（JSON）：", ""]
            for k, v in meta["body"].items():
                lines.append(f"- `{k}`：{v}")
            lines.append("")
        if meta.get("produces"):
            lines += [f"响应类型：`{meta['produces']}`", ""]
    return "\n".join(lines).rstrip() + "\n"
