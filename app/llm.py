"""OpenAI 兼容 Chat Completions 客户端（design.md §14、A5）。

- `base_url / api_key / model` 全部经 .env 配置（GLM / DeepSeek / OpenAI / Ollama 等均可）。
- 未配置时抛 LLMNotConfigured，由编排层执行降级交付（global.md §7.3）。
- API Key 不进日志与输出（NFR6）。
"""
from __future__ import annotations

import time

import requests

from . import log


class LLMNotConfigured(Exception):
    """LLM 三要素未配置齐。"""


class LLMError(Exception):
    """LLM 调用在重试后仍失败。"""


class LLMClient:
    def __init__(self, base_url: str, api_key: str, model: str,
                 timeout: int = 180, max_retries: int = 3) -> None:
        if not (base_url and api_key and model):
            raise LLMNotConfigured("LLM 未配置：需要在 .env 中填写 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL")
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.last_usage_total: int = 0

    # ---- 基础调用 ----

    def chat(self, system: str, user: str, temperature: float = 0.3,
             json_mode: bool = False) -> str:
        payload: dict = {
            "model": self.model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        last_err: Exception | None = None
        allow_json_flag = json_mode
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = requests.post(
                    self.url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                last_err = exc
                time.sleep(min(2 ** attempt, 8))
                continue
            if resp.status_code == 400 and allow_json_flag and "response_format" in resp.text:
                # 部分 OpenAI 兼容后端不支持 response_format，去掉后重试
                allow_json_flag = False
                payload.pop("response_format", None)
                continue
            if resp.status_code in (429, 500, 502, 503, 504):
                retry_after = (resp.headers.get("Retry-After") or "").strip()
                delay = (float(retry_after) if retry_after.replace(".", "", 1).isdigit()
                         else min(2 ** attempt, 8))
                last_err = LLMError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                time.sleep(min(delay, 30))
                continue
            if resp.status_code >= 400:
                raise LLMError(f"HTTP {resp.status_code}: {resp.text[:300]}")
            try:
                data = resp.json()
            except ValueError as exc:
                last_err = LLMError(f"响应非合法 JSON：{exc}")
                time.sleep(min(2 ** attempt, 8))
                continue
            usage = data.get("usage") or {}
            self.last_usage_total = int(usage.get("total_tokens") or 0)
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content")
            if not content:
                last_err = LLMError("响应缺少 choices[0].message.content")
                continue
            return content
        raise LLMError(f"LLM 调用重试 {self.max_retries} 次后仍失败：{last_err}")

    # ---- JSON 解析 ----

    @staticmethod
    def extract_json(text: str) -> dict:
        """从回复中提取第一个平衡的 JSON 对象（容忍 markdown 围栏与前后缀文字）。"""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.rstrip().endswith("```"):
                cleaned = cleaned.rstrip()[:-3]
        start = cleaned.find("{")
        if start < 0:
            raise LLMError("回复中未找到 JSON 对象")
        depth = 0
        in_str = False
        escape = False
        for i in range(start, len(cleaned)):
            ch = cleaned[i]
            if in_str:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    import json

                    try:
                        return json.loads(cleaned[start:i + 1])
                    except json.JSONDecodeError as exc:
                        raise LLMError(f"JSON 解析失败：{exc}") from exc
        raise LLMError("JSON 对象不完整（括号未闭合）")
