"""入口：python -m server [--host H] [--port P] [--dev]"""
from __future__ import annotations

import argparse
import sys

from .app import run
from .config import ServerConfig


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="server", description="GitHub-Trend-Learner 控制台后端")
    ap.add_argument("--host", default=None, help="监听地址（默认 127.0.0.1）")
    ap.add_argument("--port", type=int, default=None, help="监听端口（默认 8000）")
    ap.add_argument("--dev", action="store_true", help="开发模式：放开 CORS，配合 vite dev")
    args = ap.parse_args(argv)

    base = ServerConfig.from_env()
    cfg = ServerConfig(
        host=args.host or base.host,
        port=args.port or base.port,
        dev_mode=args.dev or base.dev_mode,
    )
    return run(cfg)


if __name__ == "__main__":
    sys.exit(main())
