"""配置加载（design.md §14）：.env + 环境变量。敏感信息不落日志（NFR6、global.md §4.2）。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

CACHE_DIR = PROJECT_ROOT / "cache"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
LOGS_DIR = PROJECT_ROOT / "logs"

# 每日任务「自动解析」仓库数上限（v1.8）：每个仓库都会调用多次 LLM，
# 若不设上界，一次 `top=100000` 的请求即可放大成巨额账单。此处为最后一道防线。
MAX_AUTO_PARSE = 50


def _strip_inline_comment(value: str) -> str:
    """剥离行内注释。

    仅当 `#` 前面是空白时才视为注释起始（`KEY=10  # 说明`），
    这样不会误伤本身含 `#` 的值（如 `#` 出现在 token 或 URL fragment 中）。
    """
    for i, ch in enumerate(value):
        if ch == "#" and i > 0 and value[i - 1] in " \t":
            return value[:i].rstrip()
    return value


def _parse_value(raw: str) -> str:
    """解析 `.env` 右值：带引号则整体取引号内内容，否则剥离行内注释。"""
    text = raw.strip()
    if text[:1] in ("'", '"'):
        quote = text[0]
        end = text.find(quote, 1)
        return text[1:end] if end > 0 else text[1:]
    return _strip_inline_comment(text).strip()


def load_env(env_path: Path | None = None) -> None:
    """把 .env 中的键值注入 os.environ（不覆盖已存在的环境变量）。"""
    path = env_path or PROJECT_ROOT / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = _parse_value(value)


def _env(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    try:
        return int(raw) if raw else default
    except ValueError:
        return default  # 非法数字按默认值处理，不让进程崩溃


@dataclass
class Settings:
    github_token: str | None
    llm_base_url: str | None
    llm_api_key: str | None
    llm_model: str | None
    smtp_host: str | None
    smtp_port: int
    smtp_user: str | None
    smtp_password: str | None
    mail_from: str | None
    mail_to: list[str]
    trending_top_n: int
    candidate_pool_size: int  # 候选池规模（发现页可选仓库数，v1.8 与每日解析数量解耦）
    concurrency: int          # 并发上限 3（design.md §8.1，已确认）
    max_retries: int          # 重试上限 3（global.md §7.2）
    max_gate_returns: int     # 质量门禁退回上限 2（global.md §6.2）

    @property
    def llm_ready(self) -> bool:
        return bool(self.llm_base_url and self.llm_api_key and self.llm_model)

    @property
    def smtp_ready(self) -> bool:
        return bool(self.smtp_host and self.mail_from and self.mail_to)

    @classmethod
    def load(cls, env_path: Path | None = None) -> "Settings":
        load_env(env_path)
        mail_to_raw = _env("MAIL_TO") or ""
        return cls(
            github_token=_env("GITHUB_TOKEN"),
            llm_base_url=_env("LLM_BASE_URL"),
            llm_api_key=_env("LLM_API_KEY"),
            llm_model=_env("LLM_MODEL"),
            smtp_host=_env("SMTP_HOST"),
            smtp_port=_env_int("SMTP_PORT", 465),
            smtp_user=_env("SMTP_USER"),
            smtp_password=_env("SMTP_PASSWORD"),
            mail_from=_env("MAIL_FROM"),
            mail_to=[x.strip() for x in mail_to_raw.split(",") if x.strip()],
            trending_top_n=_env_int("TRENDING_TOP_N", 10),
            candidate_pool_size=_env_int("CANDIDATE_POOL_SIZE", 60),
            concurrency=_env_int("CONCURRENCY", 3),
            max_retries=3,
            max_gate_returns=2,
        )
