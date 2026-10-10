"""服务端配置：路径常量与服务参数。

复用 app.config 的项目根与目录定义，避免两处维护。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
FRONTEND_DIST = FRONTEND_DIR / "dist"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
LOGS_DIR = PROJECT_ROOT / "logs"
CACHE_DIR = PROJECT_ROOT / "cache"

# 说明：六模块标识（含「一、」等序号）统一定义在 app/contracts.MODULES_ORDER。
# v1.8 之前这里有一份独立副本，改口径时需人工同步；现已删除，需要时直接从 contracts 引用。


def _int_env(name: str, default: int) -> int:
    """读取整数环境变量；非法值回落默认并告警，不让进程启动失败（v1.8）。"""
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"[warn] {name}={raw!r} 不是合法整数，已回落默认值 {default}")
        return default


@dataclass(frozen=True)
class ServerConfig:
    """HTTP 服务参数。"""

    host: str = "127.0.0.1"
    port: int = 8000
    dev_mode: bool = False

    @classmethod
    def from_env(cls) -> "ServerConfig":
        # 必须先加载 .env，否则用户在 .env 里写的 UI_HOST/UI_PORT/UI_DEV 不会生效
        # （此前只在 app.config.Settings.load() 内部调用 load_env，时序上晚于本方法 —— v1.8 修复）
        from app.config import load_env

        load_env()
        return cls(
            host=os.getenv("UI_HOST", "127.0.0.1"),
            port=_int_env("UI_PORT", 8000),
            dev_mode=os.getenv("UI_DEV", "").lower() in ("1", "true", "yes"),
        )

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def dist_ready(self) -> bool:
        return (FRONTEND_DIST / "index.html").is_file()
