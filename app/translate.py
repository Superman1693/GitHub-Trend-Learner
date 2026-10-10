"""候选仓库描述的中文翻译（免费翻译引擎 + 内容寻址缓存）。

**不消耗任何 LLM token**：走公开翻译引擎（有道 / MyMemory），并做磁盘缓存。

成本与稳定性策略：
  1. **内容寻址缓存**：以原文 SHA1 为键持久化到 `cache/translations.json`，
     同一段文本整个生命周期**只翻译一次**，重复运行零请求、零成本；
  2. **引擎降级链**：有道 → MyMemory，任一可用即返回；单个失败自动切换；
  3. **并发受限**：默认 6 路并发，礼貌请求、失败自动重试；
  4. **失败不阻断**：拿不到译文时保留英文原文，绝不阻断主流程；
  5. **跳过无需翻译项**：空文本、已含中文的文本直接跳过。

本模块不做任何网络探测，只被显式调用时才发起请求。
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from . import log
from .config import CACHE_DIR
from .fsutil import atomic_write_text

CACHE_FILE = CACHE_DIR / "translations.json"
MAX_TEXT_LEN = 800          # 单条截断上限，超长描述不浪费请求
DEFAULT_WORKERS = 6
RETRY_PER_ENGINE = 2

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

YOUDAO_URL = "https://aidemo.youdao.com/trans"
MYMEMORY_URL = "https://api.mymemory.translated.net/get"

_CJK = re.compile(r"[\u4e00-\u9fff]")


def _key(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def has_chinese(text: str) -> bool:
    return bool(_CJK.search(text or ""))


# 专有名词修正：免费引擎常把技术专名意译，这里做保守回填（幂等，可重复执行）
_POST_EDIT: tuple[tuple[str, str], ...] = (
    ("克劳德代码", "Claude Code"),
    ("克劳德", "Claude"),
    ("代码克斯", "Codex"),
    ("科德克斯", "Codex"),
    ("副驾驶", "Copilot"),
    ("美人鱼的泔水", "Mermaid 的冗余代码"),
    ("美人鱼", "Mermaid"),
    ("座席", "智能体"),
    ("人工智能模型", "AI 模型"),
    ("代理目录", "agents 目录"),
    ("GitHubCopilot", "GitHub Copilot"),
    ("Github", "GitHub"),
    ("开源存储库", "开源仓库"),
)

# 中文标点集合：用于清理「中文标点 + 多余空格 + 英文」这类排版瑕疵
_CN_PUNCT_LEFT = "，。；：！？、）】》」"
_CN_PUNCT_RIGHT = "，。；：！？、（【《「"
_SPACE_AFTER = re.compile(rf"([{_CN_PUNCT_LEFT}])\s+")
_SPACE_BEFORE = re.compile(rf"\s+([{_CN_PUNCT_RIGHT}])")
_MULTI_SPACE = re.compile(r"[ \t]{2,}")


def _polish(text: str) -> str:
    """译文后处理：专名回填 + 中文标点周边空格清理。幂等。"""
    out = text
    for bad, good in _POST_EDIT:
        if bad in out:
            out = out.replace(bad, good)
    out = _SPACE_AFTER.sub(r"\1", out)
    out = _SPACE_BEFORE.sub(r"\1", out)
    out = _MULTI_SPACE.sub(" ", out)
    return out.strip()


# ---------------- 缓存 ----------------

def load_cache() -> dict[str, str]:
    if not CACHE_FILE.is_file():
        return {}
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_cache(cache: dict[str, str]) -> None:
    try:
        atomic_write_text(CACHE_FILE, json.dumps(cache, ensure_ascii=False, indent=0))
    except OSError:
        pass


def normalize_cache() -> int:
    """把缓存中已有译文统一过一遍后处理（专名/标点）；返回更新条数。"""
    cache = load_cache()
    changed = 0
    for k, v in list(cache.items()):
        polished = _polish(v)
        if polished != v:
            cache[k] = polished
            changed += 1
    if changed:
        save_cache(cache)
    return changed


# ---------------- 引擎 ----------------

def _youdao(text: str, timeout: int = 12) -> str | None:
    resp = requests.post(
        YOUDAO_URL,
        data={"q": text, "from": "en", "to": "zh-CHS"},
        headers={"User-Agent": _UA},
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    if str(data.get("errorCode")) not in ("0", "None"):
        return None
    lines = data.get("translation") or []
    out = "".join(lines).strip()
    return out or None


def _mymemory(text: str, timeout: int = 12) -> str | None:
    resp = requests.get(
        MYMEMORY_URL,
        params={"q": text, "langpair": "en|zh-CN"},
        headers={"User-Agent": _UA},
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    out = ((data.get("responseData") or {}).get("translatedText") or "").strip()
    if not out or "MYMEMORY WARNING" in out.upper() or "QUERY LENGTH LIMIT" in out.upper():
        return None
    return out


# 顺序即优先级：有道质量稳定、限流宽松；MyMemory 作兜底
ENGINES: tuple[tuple[str, object], ...] = (("youdao", _youdao), ("mymemory", _mymemory))


def _translate_one(text: str) -> tuple[str | None, str]:
    """返回 (译文, 命中引擎名)；全部失败返回 (None, '')。"""
    for name, fn in ENGINES:
        for _ in range(RETRY_PER_ENGINE):
            try:
                out = fn(text)  # type: ignore[operator]
            except Exception:  # noqa: BLE001 - 换引擎重试
                out = None
            if out:
                return out, name
            time.sleep(0.4)
    return None, ""


# ---------------- 对外接口 ----------------

def translate_texts(
    texts: list[str],
    *,
    workers: int = DEFAULT_WORKERS,
    persist: bool = True,
) -> dict[str, str]:
    """把一批文本翻译成中文，返回 {原文: 译文}。

    命中缓存 / 已含中文的条目直接返回，不发起任何请求。
    """
    cache = load_cache()
    result: dict[str, str] = {}
    pending: list[str] = []

    for raw in texts:
        text = (raw or "").strip()
        if not text:
            continue
        if has_chinese(text):
            result[text] = text
            continue
        cached = cache.get(_key(text))
        if cached:
            result[text] = _polish(cached)
            continue
        if text not in pending:
            pending.append(text)

    if not pending:
        return result

    workers = max(1, min(workers, len(pending)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_translate_one, t[:MAX_TEXT_LEN]): t for t in pending}
        for fut in as_completed(futures):
            src = futures[fut]
            try:
                zh, _engine = fut.result()
            except Exception:  # noqa: BLE001
                zh = None
            if zh:
                zh = _polish(zh)
                cache[_key(src)] = zh
                result[src] = zh

    if persist and result:
        save_cache(cache)
    log.console(
        f"  [翻译] 待译 {len(pending)} 条，新增译文 "
        f"{sum(1 for t in pending if t in result)} 条（缓存累计 {len(cache)} 条）"
    )
    return result


def translate_items(
    items: list[dict],
    *,
    source_field: str = "description",
    target_field: str = "description_zh",
    workers: int = DEFAULT_WORKERS,
) -> int:
    """就地给候选条目补 `description_zh`；返回新增译文条数。"""
    texts = [(it.get(source_field) or "").strip() for it in items]
    if not any(texts):
        return 0
    mapping = translate_texts(texts, workers=workers)
    filled = 0
    for it in items:
        src = (it.get(source_field) or "").strip()
        zh = mapping.get(src)
        if zh:
            it[target_field] = zh
            filled += 1
    return filled
