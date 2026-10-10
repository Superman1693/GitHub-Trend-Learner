"""本地预览界面：把 outputs/ 下的解读文档渲染成网页，便于人工测试。

用法：
    F:\\Python\\Python-3.13.2\\python.exe preview.py
    然后浏览器打开 http://127.0.0.1:8765

仅用 Python 标准库，无额外依赖。不修改任何产出文件，只读。
"""
from __future__ import annotations

import argparse
import html
import re
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"

CSS = """
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;
     font-size:15px;line-height:1.75;color:#2c2c2a;background:#f7f6f3}
.wrap{max-width:920px;margin:0 auto;padding:24px 20px 80px}
header{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;
       border-bottom:1px solid #e0deda;padding-bottom:12px;margin-bottom:24px}
h1{font-size:20px;font-weight:600;margin:0}
.sub{color:#888780;font-size:13px}
a{color:#185fa5;text-decoration:none}
a:hover{text-decoration:underline}
.card{background:#fff;border:1px solid #e0deda;border-radius:10px;
      padding:12px 16px;margin-bottom:10px;display:flex;justify-content:space-between;
      align-items:center;gap:12px}
.card .meta{color:#888780;font-size:12px;white-space:nowrap}
.date{font-size:13px;font-weight:600;color:#5f5e5a;margin:22px 0 8px}
.doc{background:#fff;border:1px solid #e0deda;border-radius:10px;padding:28px 32px}
.doc h1{font-size:22px;margin:0 0 8px}
.doc h2{font-size:18px;margin:28px 0 10px;padding-top:14px;border-top:1px solid #efedea}
.doc h3{font-size:15px;margin:20px 0 8px;color:#444441}
.doc h4{font-size:14px;margin:16px 0 6px;color:#5f5e5a}
.doc p{margin:8px 0}
.doc code{background:#f1efe8;padding:2px 5px;border-radius:4px;
          font-family:Consolas,"Courier New",monospace;font-size:13px;color:#993c1d}
.doc pre{background:#f1efe8;border:1px solid #e0deda;border-radius:8px;
         padding:12px 14px;overflow-x:auto;margin:10px 0}
.doc pre code{background:none;padding:0;color:#2c2c2a;font-size:13px;line-height:1.6}
.doc blockquote{margin:10px 0;padding:8px 14px;border-left:3px solid #b5d4f4;
                background:#f4f8fd;color:#444441;border-radius:0 6px 6px 0}
.doc blockquote p{margin:2px 0}
.doc table{border-collapse:collapse;width:100%;margin:12px 0;font-size:14px}
.doc th,.doc td{border:1px solid #e0deda;padding:7px 10px;text-align:left;vertical-align:top}
.doc th{background:#f7f6f3;font-weight:600}
.doc ul,.doc ol{margin:8px 0;padding-left:24px}
.doc li{margin:3px 0}
.doc hr{border:none;border-top:1px solid #e0deda;margin:22px 0}
.bar{display:flex;gap:10px;align-items:center;margin-bottom:16px;flex-wrap:wrap}
.btn{display:inline-block;padding:6px 14px;background:#fff;border:1px solid #e0deda;
     border-radius:8px;font-size:13px;color:#444441}
.btn:hover{background:#f1efe8;text-decoration:none}
.empty{color:#888780;padding:40px 0;text-align:center}
"""


def esc(s: str) -> str:
    return html.escape(s, quote=False)


def inline(s: str) -> str:
    s = esc(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", s)
    return s


def md_to_html(md: str) -> str:
    lines = md.splitlines()
    out: list[str] = []
    i, in_code, fence, buf = 0, False, "", []

    def flush_code() -> None:
        out.append("<pre><code>" + esc("\n".join(buf)) + "</code></pre>")

    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()

        m = re.match(r"^(`{3,})", stripped)
        if m:
            if not in_code:
                in_code, fence, buf = True, m.group(1), []
            elif stripped.startswith(fence):
                in_code = False
                flush_code()
            else:
                buf.append(raw)
            i += 1
            continue
        if in_code:
            buf.append(raw)
            i += 1
            continue

        s = raw.rstrip()
        if not s.strip():
            i += 1
            continue

        if s.lstrip().startswith("|") and i + 1 < len(lines) and \
                re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            head = [c.strip() for c in s.strip().strip("|").split("|")]
            i += 2
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            t = ["<table><thead><tr>"]
            t += [f"<th>{inline(h)}</th>" for h in head]
            t.append("</tr></thead><tbody>")
            for r in rows:
                t.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
            t.append("</tbody></table>")
            out.append("".join(t))
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{inline(m.group(2))}</h{lvl}>")
            i += 1
            continue

        if s.lstrip().startswith(">"):
            b = []
            while i < len(lines) and lines[i].lstrip().startswith(">"):
                b.append(lines[i].lstrip()[1:].strip())
                i += 1
            out.append("<blockquote>" + "<br>".join(inline(x) for x in b) + "</blockquote>")
            continue

        for pat, tag in ((r"^\s*[-*]\s+", "ul"), (r"^\s*\d+\.\s+", "ol")):
            if re.match(pat, s):
                b = []
                while i < len(lines) and re.match(pat, lines[i]):
                    b.append(re.sub(pat, "", lines[i]))
                    i += 1
                out.append(f"<{tag}>" + "".join(f"<li>{inline(x)}</li>" for x in b) + f"</{tag}>")
                break
        else:
            out.append(f"<p>{inline(s)}</p>")
            i += 1

    if in_code and buf:
        flush_code()
    return "\n".join(out)


def page(title: str, body: str) -> bytes:
    return (f"<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{esc(title)}</title><style>{CSS}</style></head>"
            f"<body><div class='wrap'>{body}</div></body></html>").encode("utf-8")


def index_html() -> bytes:
    if not OUT.exists():
        return page("预览", "<div class='empty'>outputs/ 目录不存在，先跑一次任务。</div>")
    days = sorted([d for d in OUT.iterdir() if d.is_dir()], reverse=True)
    if not days:
        return page("预览", "<div class='empty'>outputs/ 下暂无产出，先跑一次任务。</div>")
    body = ["<header><h1>解读文档预览</h1><span class='sub'>outputs/ 只读预览</span></header>"]
    total = 0
    for d in days:
        files = sorted(d.glob("*.md"))
        if not files:
            continue
        body.append(f"<div class='date'>{esc(d.name)}　共 {len(files)} 份</div>")
        for f in files:
            size = f.stat().st_size
            total += 1
            body.append(
                f"<div class='card'><a href='/view?f={esc(d.name)}/{esc(f.name)}'>{esc(f.name)}</a>"
                f"<span class='meta'>{size / 1024:.1f} KB</span></div>"
            )
    body.append(f"<div class='date'>合计 {total} 份文档</div>")
    return page("解读文档预览", "".join(body))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # 静音，避免刷屏
        pass

    def do_GET(self) -> None:
        u = urlparse(self.path)
        if u.path == "/":
            self._send(index_html())
            return
        if u.path == "/view":
            rel = (parse_qs(u.query).get("f") or [""])[0]
            target = (OUT / rel).resolve()
            if not str(target).startswith(str(OUT.resolve())) or not target.is_file():
                self._send(page("未找到", "<div class='empty'>文件不存在。</div>"), 404)
                return
            raw = target.read_text(encoding="utf-8", errors="replace")
            bar = ("<div class='bar'><a class='btn' href='/'>&larr; 返回列表</a>"
                   f"<span class='sub'>{esc(rel)}</span></div>")
            self._send(page(rel, bar + "<div class='doc'>" + md_to_html(raw) + "</div>"))
            return
        self._send(page("未找到", "<div class='empty'>404</div>"), 404)

    def _send(self, data: bytes, code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    ap = argparse.ArgumentParser(description="解读文档本地预览")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    url = f"http://127.0.0.1:{args.port}/"
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"预览已启动：{url}")
    print(f"监控目录：{OUT}")
    print("按 Ctrl+C 停止")
    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
