"""翻译模块（app/translate.py）测试。

引擎调用一律 mock，测试不触网。重点覆盖：
- 内容寻址缓存：同一文本只翻译一次
- 已含中文 / 空文本直接跳过
- 引擎降级链
- 后处理（专有名词回填 + 中文标点空格清理）幂等
"""
from __future__ import annotations

import pytest

from app import translate


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    """把缓存文件指到临时目录，避免污染真实 cache/。"""
    monkeypatch.setattr(translate, "CACHE_FILE", tmp_path / "translations.json")
    yield


def test_has_chinese():
    assert translate.has_chinese("中文")
    assert not translate.has_chinese("english only")
    assert not translate.has_chinese("")


def test_skips_chinese_and_empty(monkeypatch):
    calls: list[str] = []

    def fake(text, timeout=12):
        calls.append(text)
        return "译:" + text

    monkeypatch.setattr(translate, "ENGINES", (("fake", fake),))
    out = translate.translate_texts(["已经是中文", "", "   ", "hello"])
    assert out["已经是中文"] == "已经是中文"
    assert out["hello"] == "译:hello"
    assert calls == ["hello"], "已含中文/空文本不应触发引擎调用"


def test_cache_prevents_second_request(monkeypatch):
    calls: list[str] = []

    def fake(text, timeout=12):
        calls.append(text)
        return "译文"

    monkeypatch.setattr(translate, "ENGINES", (("fake", fake),))
    translate.translate_texts(["same text"])
    translate.translate_texts(["same text"])
    assert len(calls) == 1, "第二次应命中缓存，不重复请求"


def test_engine_fallback_chain(monkeypatch):
    def broken(text, timeout=12):
        raise RuntimeError("engine down")

    def backup(text, timeout=12):
        return "备用译文"

    monkeypatch.setattr(translate, "ENGINES", (("broken", broken), ("backup", backup)))
    out = translate.translate_texts(["hello world"])
    assert out["hello world"] == "备用译文"


def test_all_engines_failed_keeps_original(monkeypatch):
    def broken(text, timeout=12):
        raise RuntimeError("down")

    monkeypatch.setattr(translate, "ENGINES", (("broken", broken),))
    monkeypatch.setattr(translate, "RETRY_PER_ENGINE", 1)
    out = translate.translate_texts(["hello world"])
    assert "hello world" not in out        # 没有译文
    assert translate.translate_items([{"description": "hello world"}]) == 0


@pytest.mark.parametrize("raw,expected", [
    ("克劳德代码 很好用", "Claude Code 很好用"),
    ("美人鱼的泔水", "Mermaid 的冗余代码"),
    ("使用副驾驶", "使用Copilot"),
    ("， GitHub Copilot ，", "，GitHub Copilot，"),
    ("没有阴影 。 没有冗余", "没有阴影。没有冗余"),
])
def test_polish(raw, expected):
    assert translate._polish(raw) == expected


def test_polish_is_idempotent():
    text = "编辑图设计克劳德代码，Codex， GitHub副驾驶"
    once = translate._polish(text)
    assert translate._polish(once) == once


def test_normalize_cache_rewrites_existing_values(monkeypatch):
    translate.save_cache({"k1": "克劳德代码 。 ", "k2": "正常译文"})
    changed = translate.normalize_cache()
    cache = translate.load_cache()
    assert changed == 1
    assert cache["k1"] == "Claude Code。"
    assert cache["k2"] == "正常译文"


def test_translate_items_fills_target_field(monkeypatch):
    monkeypatch.setattr(translate, "ENGINES", (("fake", lambda t, timeout=12: "中文"),))
    items = [{"description": "hello"}, {"description": "中文原文"}, {"description": ""}]
    filled = translate.translate_items(items)
    assert filled == 2
    assert items[0]["description_zh"] == "中文"
    assert items[1]["description_zh"] == "中文原文"
    assert "description_zh" not in items[2]
