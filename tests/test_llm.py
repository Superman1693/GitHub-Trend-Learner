"""LLM 客户端（app/llm.py）测试。

该模块此前覆盖率仅 19%，而它是全流程的咽喉：
重试策略、response_format 降级、以及 extract_json 的花括号配对
（字符串/转义处理）任何一处出错都会让所有仓库解析失败。

全部通过 mock requests.post 完成，不触网。
"""
from __future__ import annotations

import json

import pytest

from app import llm as llm_mod
from app.llm import LLMClient, LLMError, LLMNotConfigured


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(llm_mod.time, "sleep", lambda *_: None)


def _client(**kw) -> LLMClient:
    return LLMClient("https://api.example.com/v1", "sk-test", "test-model", **kw)


class _Resp:
    def __init__(self, status=200, payload=None, text="", headers=None):
        self.status_code = status
        self._payload = payload
        self.text = text or json.dumps(payload or {})
        self.headers = headers or {}

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def _ok(content="hello", tokens=42) -> _Resp:
    return _Resp(200, {"choices": [{"message": {"content": content}}],
                       "usage": {"total_tokens": tokens}})


# ---------------- 配置校验 ----------------

@pytest.mark.parametrize("kwargs", [
    {"base_url": "", "api_key": "k", "model": "m"},
    {"base_url": "u", "api_key": "", "model": "m"},
    {"base_url": "u", "api_key": "k", "model": ""},
])
def test_requires_all_three_configs(kwargs):
    with pytest.raises(LLMNotConfigured):
        LLMClient(kwargs["base_url"], kwargs["api_key"], kwargs["model"])


def test_url_joined_and_trimmed():
    c = LLMClient("https://api.example.com/v1/", "k", "m")
    assert c.url == "https://api.example.com/v1/chat/completions"


# ---------------- chat 正常路径 ----------------

def test_chat_returns_content_and_tokens(monkeypatch):
    monkeypatch.setattr(llm_mod.requests, "post", lambda *a, **k: _ok("答案", 128))
    c = _client()
    assert c.chat("sys", "user") == "答案"
    assert c.last_usage_total == 128


def test_chat_sends_json_mode_flag(monkeypatch):
    seen = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen.update(json or {})
        return _ok()

    monkeypatch.setattr(llm_mod.requests, "post", fake_post)
    _client().chat("s", "u", json_mode=True)
    assert seen["response_format"] == {"type": "json_object"}
    assert seen["messages"][0]["role"] == "system"
    assert seen["temperature"] == 0.3


# ---------------- chat 降级与重试 ----------------

def test_chat_retries_without_response_format_on_400(monkeypatch):
    """部分 OpenAI 兼容后端不支持 response_format，应去掉该字段后重试。"""
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(dict(json or {}))
        if "response_format" in (json or {}):
            return _Resp(400, {"error": "unsupported"}, text="response_format not supported")
        return _ok("降级成功")

    monkeypatch.setattr(llm_mod.requests, "post", fake_post)
    out = _client().chat("s", "u", json_mode=True)
    assert out == "降级成功"
    assert len(calls) == 2
    assert "response_format" in calls[0] and "response_format" not in calls[1]


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_chat_retries_on_transient_status(monkeypatch, status):
    seq = [_Resp(status, {"e": 1}, text="boom"), _ok("重试成功")]

    def fake_post(*a, **k):
        return seq.pop(0)

    monkeypatch.setattr(llm_mod.requests, "post", fake_post)
    assert _client(max_retries=2).chat("s", "u") == "重试成功"


def test_chat_honours_retry_after_header(monkeypatch):
    waited: list[float] = []
    monkeypatch.setattr(llm_mod.time, "sleep", lambda s: waited.append(s))
    seq = [_Resp(429, {"e": 1}, headers={"Retry-After": "3"}), _ok()]

    monkeypatch.setattr(llm_mod.requests, "post", lambda *a, **k: seq.pop(0))
    _client(max_retries=2).chat("s", "u")
    assert waited and waited[0] == 3.0


def test_chat_raises_immediately_on_permanent_error(monkeypatch):
    """401 这类确定性错误不该无脑重试（global.md §7.2）。"""
    calls = []

    def fake_post(*a, **k):
        calls.append(1)
        return _Resp(401, {"error": "bad key"}, text="invalid api key")

    monkeypatch.setattr(llm_mod.requests, "post", fake_post)
    with pytest.raises(LLMError) as exc:
        _client(max_retries=3).chat("s", "u")
    assert "401" in str(exc.value)
    assert len(calls) == 1, "确定性错误不应重试"


def test_chat_retries_on_network_error_then_fails(monkeypatch):
    import requests

    monkeypatch.setattr(llm_mod.requests, "post",
                        lambda *a, **k: (_ for _ in ()).throw(requests.RequestException("boom")))
    with pytest.raises(LLMError):
        _client(max_retries=2).chat("s", "u")


def test_chat_retries_on_non_json_body(monkeypatch):
    seq = [_Resp(200, None, text="<html>502</html>"), _ok("恢复")]

    monkeypatch.setattr(llm_mod.requests, "post", lambda *a, **k: seq.pop(0))
    assert _client(max_retries=2).chat("s", "u") == "恢复"


def test_chat_retries_on_missing_content(monkeypatch):
    seq = [_Resp(200, {"choices": [{"message": {}}]}), _ok("有内容了")]

    monkeypatch.setattr(llm_mod.requests, "post", lambda *a, **k: seq.pop(0))
    assert _client(max_retries=2).chat("s", "u") == "有内容了"


def test_chat_exhausted_retries_raises(monkeypatch):
    monkeypatch.setattr(llm_mod.requests, "post",
                        lambda *a, **k: _Resp(503, {"e": 1}, text="down"))
    with pytest.raises(LLMError) as exc:
        _client(max_retries=2).chat("s", "u")
    assert "重试" in str(exc.value)


# ---------------- extract_json ----------------

def test_extract_json_plain():
    assert LLMClient.extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_strips_markdown_fence():
    raw = '```json\n{"a": 1}\n```'
    assert LLMClient.extract_json(raw) == {"a": 1}


def test_extract_json_ignores_surrounding_prose():
    raw = '好的，这是结果：{"a": 1} 希望有帮助。'
    assert LLMClient.extract_json(raw) == {"a": 1}


def test_extract_json_handles_nested_objects():
    raw = '{"outer": {"inner": {"deep": [1, 2]}}}'
    assert LLMClient.extract_json(raw)["outer"]["inner"]["deep"] == [1, 2]


def test_extract_json_ignores_braces_inside_strings():
    """花括号出现在字符串里时不应影响配对——这是最易写错的分支。"""
    raw = '{"text": "这里有 } 和 { 但不是结构", "n": 1}'
    parsed = LLMClient.extract_json(raw)
    assert parsed["text"] == "这里有 } 和 { 但不是结构"
    assert parsed["n"] == 1


def test_extract_json_handles_escaped_quote_in_string():
    raw = '{"text": "他说\\"你好\\"", "n": 2}'
    assert LLMClient.extract_json(raw)["n"] == 2


def test_extract_json_handles_backslash_before_quote():
    """反斜杠转义链：`\\\\` 后的引号仍是字符串结束符。"""
    raw = '{"path": "C:\\\\dir", "n": 3}'
    assert LLMClient.extract_json(raw)["n"] == 3


def test_extract_json_raises_without_object():
    with pytest.raises(LLMError):
        LLMClient.extract_json("完全没有 JSON")


def test_extract_json_raises_on_unclosed_object():
    with pytest.raises(LLMError):
        LLMClient.extract_json('{"a": 1')


def test_extract_json_raises_on_invalid_json():
    with pytest.raises(LLMError):
        LLMClient.extract_json("{不是合法 JSON}")
