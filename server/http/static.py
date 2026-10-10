"""静态资源服务：托管前端构建产物，带 SPA 回退。

修复「打开页面 404」的关键三点：
1. `/api/*` 永不回退到 index.html —— 接口 404 必须如实返回 JSON 404，不能被伪装成 200 的 HTML。
2. 非 API 路径若命中 dist 内真实文件则直接返回；否则回退 index.html，
   这样前端客户端路由（如 /documents/2026-10-08/xxx）刷新时不会 404。
3. dist 未构建时返回 HTTP 200 的引导页（说明怎么构建），而不是 404 ——
   让用户一眼看出是「没构建」而不是「服务坏了」。
"""
from __future__ import annotations

from pathlib import Path

from ..config import FRONTEND_DIST, PROJECT_ROOT
from .response import Response, file_response, html_response

_GUIDE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>前端尚未构建</title>
<style>
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
     font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;background:#f7f6f3;color:#2c2c2a}
.box{max-width:620px;padding:32px 36px;background:#fff;border:1px solid #e0deda;border-radius:12px}
h1{font-size:19px;margin:0 0 12px}
p{line-height:1.8;color:#444441;font-size:14px}
pre{background:#f1efe8;border:1px solid #e0deda;border-radius:8px;padding:12px 14px;
    overflow-x:auto;font-size:13px;line-height:1.7}
code{font-family:Consolas,"Courier New",monospace}
.note{color:#888780;font-size:13px;margin-top:16px}
</style></head><body><div class="box">
<h1>前端尚未构建</h1>
<p>后端服务已正常启动，但没有找到前端构建产物 <code>frontend/dist/index.html</code>。</p>
<p>请执行：</p>
<pre><code>cd frontend
npm install
npm run build</code></pre>
<p>完成后刷新本页即可。若在开发模式下工作，可另开一个终端执行 <code>npm run dev</code>（默认 5173 端口，已配置 API 代理）。</p>
<p class="note">或者直接使用一键脚本：<code>python start_ui.py</code>（会自动完成构建）。</p>
</div></body></html>
"""


def _resolve_within_dist(rel: str) -> Path | None:
    """把相对路径解析到 dist 内，越界或不存在返回 None（防目录穿越）。

    必须用 `Path.is_relative_to` 而非字符串 `startswith`：后者会把同级目录
    `dist-evil` 误判为在 `dist` 内（`".../dist-evil".startswith(".../dist")` 为真），
    从而绕过守卫（v1.8 修复）。
    """
    if not rel or rel.startswith("/api"):
        return None
    candidate = (FRONTEND_DIST / rel.lstrip("/")).resolve()
    dist_root = FRONTEND_DIST.resolve()
    if not candidate.is_relative_to(dist_root):
        return None
    return candidate if candidate.is_file() else None


def serve_static(path: str) -> Response | None:
    """尝试以静态资源响应；返回 None 表示应交给 API 路由处理。"""
    if path.startswith("/api"):
        return None

    hit = _resolve_within_dist(path)
    if hit is not None:
        return file_response(hit)

    index = FRONTEND_DIST / "index.html"
    if index.is_file():
        # SPA 回退：客户端路由刷新、深链接直接访问都能命中
        return file_response(index)

    return html_response(_GUIDE)


def dist_summary() -> dict[str, object]:
    index = FRONTEND_DIST / "index.html"
    return {
        "built": index.is_file(),
        "dist_path": str(FRONTEND_DIST.relative_to(PROJECT_ROOT)),
        "index_mtime": index.stat().st_mtime if index.is_file() else None,
    }
