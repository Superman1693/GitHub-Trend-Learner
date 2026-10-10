"""一键启动可视化控制台。

作用：
  1. 检查前端依赖与构建产物，缺失时自动安装并构建
  2. 启动后端服务（API + 静态资源托管）
  3. 自动打开浏览器

用法：
    python start_ui.py                 # 默认 127.0.0.1:8000
    python start_ui.py --port 9000     # 指定端口
    python start_ui.py --no-browser    # 不自动打开浏览器
    python start_ui.py --skip-build    # 跳过构建检查，直接启动
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"
DIST_INDEX = FRONTEND / "dist" / "index.html"
NODE_MODULES = FRONTEND / "node_modules"


def _say(msg: str) -> None:
    print(msg, flush=True)


def _run(cmd: list[str], cwd: Path) -> bool:
    """执行外部命令；返回是否成功。"""
    try:
        result = subprocess.run(cmd, cwd=str(cwd), shell=(sys.platform == "win32"))
        return result.returncode == 0
    except FileNotFoundError:
        return False


def ensure_frontend(force: bool = False) -> bool:
    """确保前端依赖与构建产物就绪。"""
    npm = shutil.which("npm")
    if npm is None:
        _say("⚠ 未找到 npm，无法自动构建前端。")
        _say("  请安装 Node.js 18+，或手动执行：cd frontend && npm install && npm run build")
        return False

    if not NODE_MODULES.is_dir():
        _say("→ 首次运行，正在安装前端依赖（可能需要几分钟）…")
        if not _run([npm, "install", "--no-audit", "--no-fund"], FRONTEND):
            _say("✗ 依赖安装失败，请检查网络后重试。")
            return False

    if force or not DIST_INDEX.is_file():
        _say("→ 正在构建前端…")
        if not _run([npm, "run", "build"], FRONTEND):
            _say("✗ 前端构建失败，请查看上方报错。")
            return False

    _say("✓ 前端产物就绪")
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="启动 GitHub-Trend-Learner 可视化控制台")
    ap.add_argument("--host", default=None, help="监听地址（默认 127.0.0.1）")
    ap.add_argument("--port", type=int, default=None, help="监听端口（默认 8000）")
    ap.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    ap.add_argument("--skip-build", action="store_true", help="跳过前端构建检查")
    ap.add_argument("--rebuild", action="store_true", help="强制重新构建前端")
    args = ap.parse_args(argv)

    _say("=" * 58)
    _say("  GitHub-Trend-Learner 可视化控制台")
    _say("=" * 58)

    if args.skip_build:
        if not DIST_INDEX.is_file():
            _say("⚠ 跳过了构建检查，但未找到前端产物，将显示引导页。")
    elif not ensure_frontend(force=args.rebuild):
        _say("")
        _say("继续启动后端（前端未就绪时会显示构建引导页）。")

    from server.app import run
    from server.config import ServerConfig

    base = ServerConfig.from_env()
    cfg = ServerConfig(
        host=args.host or base.host,
        port=args.port or base.port,
        dev_mode=base.dev_mode,
    )

    if not args.no_browser:
        try:
            webbrowser.open(cfg.base_url)
        except Exception:
            pass

    return run(cfg)


if __name__ == "__main__":
    sys.exit(main())
