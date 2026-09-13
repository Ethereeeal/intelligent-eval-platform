"""LLM 客户端（OpenAI 兼容 API）。

- 使用 openai 库，兼容千问 / DeepSeek / vLLM 等 OpenAI 兼容端点（SPEC §5.2）
- 超时、连接、限流和 5xx 最多重试 1 次，默认单次超时 30s；均可通过环境变量调整
- 返回内容解析为 JSON 数组，非标准 JSON 尝试修复（验收 F13）
- 未安装 openai 库，或 LLM_API_KEY 为占位符 "sk-xxx" 时进入 offline 模式：
  由 eiu_extractor 使用确定性规则抽取，保证离线 / 无 API Key 环境可演示。
"""
from __future__ import annotations

import json
import logging
import re
import time
from uuid import uuid4

from modules.shared.core.config import settings


logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """LLM 调用 / 解析失败。"""


class LLMClient:
    def __init__(self) -> None:
        self.api_base = settings.llm_api_base
        self.api_key = settings.llm_api_key
        self.model = settings.llm_model
        self.temperature = settings.llm_temperature
        self.max_tokens = settings.llm_max_tokens
        self.timeout_seconds = settings.eiu_llm_timeout_seconds
        self.max_attempts = settings.eiu_llm_max_attempts

        self._openai = None
        self._client = None
        self.use_offline = False
        try:
            import openai

            self._openai = openai
        except ImportError:
            self._openai = None

        if self._openai is None:
            self.use_offline = True
        elif not self.api_key or self.api_key.startswith("sk-xxx"):
            self.use_offline = True
        else:
            # max_retries=0：重试次数由本类 chat() 统一、显式控制。
            self._client = self._openai.OpenAI(
                api_key=self.api_key,
                base_url=self.api_base,
                timeout=self.timeout_seconds,
                max_retries=0,
            )

    @property
    def mode(self) -> str:
        return "offline" if self.use_offline else "llm"

    def chat(
        self,
        messages: list[dict],
        response_format: dict | None = None,
    ) -> str:
        """发送聊天请求；只对瞬时故障做一次有界重试，不记录提示词或密钥。"""
        if self.use_offline:
            raise LLMError("LLM 未配置（缺 openai 库或 API Key 为占位符），无法调用 chat()")
        if self._client is None:
            raise LLMError("LLM 客户端未初始化")

        last_exc: Exception | None = None
        call_id = uuid4().hex[:16]
        input_chars = sum(len(str(message.get("content") or "")) for message in messages)
        started = time.monotonic()
        for attempt in range(self.max_attempts):
            attempt_started = time.monotonic()
            try:
                kwargs: dict = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": self.temperature,
                    "max_tokens": self.max_tokens,
                }
                if response_format is not None:
                    kwargs["response_format"] = response_format
                response = self._client.chat.completions.create(**kwargs)
                content = response.choices[0].message.content or ""
                finish_reason = getattr(response.choices[0], "finish_reason", None)
                if finish_reason not in {"stop", "length", "tool_calls", "content_filter", "function_call"}:
                    finish_reason = "unknown"
                usage = getattr(response, "usage", None)
                tokens = {
                    key: value if type(value) is int else None
                    for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                    for value in [getattr(usage, key, None)]
                }
                logger.info(
                    "EIU LLM call completed call_id=%s attempt=%s attempt_ms=%s total_ms=%s "
                    "input_chars=%s output_chars=%s finish_reason=%s tokens=%s",
                    call_id, attempt + 1, int((time.monotonic() - attempt_started) * 1000),
                    int((time.monotonic() - started) * 1000), input_chars, len(content),
                    finish_reason, tokens,
                    extra={"model": self.model, "attempt": attempt + 1, "elapsed_ms": int((time.monotonic() - started) * 1000)},
                )
                return content
            except Exception as exc:  # noqa: BLE001 — 网络 / 超时 / 上游错误统一重试
                last_exc = exc
                retryable = self._is_retryable(exc)
                status_code = getattr(exc, "status_code", None)
                if type(status_code) is not int:
                    status_code = None
                logger.warning(
                    "EIU LLM call failed call_id=%s attempt=%s/%s attempt_ms=%s total_ms=%s "
                    "timeout_seconds=%s input_chars=%s max_tokens=%s error_type=%s "
                    "status_code=%s retryable=%s will_retry=%s",
                    call_id, attempt + 1, self.max_attempts,
                    int((time.monotonic() - attempt_started) * 1000),
                    int((time.monotonic() - started) * 1000), self.timeout_seconds,
                    input_chars, self.max_tokens, type(exc).__name__, status_code,
                    retryable, retryable and attempt + 1 < self.max_attempts,
                    extra={
                        "model": self.model,
                        "attempt": attempt + 1,
                        "elapsed_ms": int((time.monotonic() - started) * 1000),
                        "error_type": type(exc).__name__,
                        "retryable": retryable,
                    },
                )
                if not retryable or attempt + 1 >= self.max_attempts:
                    break
                time.sleep(1)
        raise LLMError(
            f"LLM 调用失败（{type(last_exc).__name__ if last_exc else 'UnknownError'}，"
            f"尝试 {min(self.max_attempts, attempt + 1)} 次）"
        )

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        """仅重试超时、连接失败、限流和 5xx；请求/鉴权错误应立即失败。"""
        status = getattr(exc, "status_code", None)
        if status in {408, 429} or isinstance(status, int) and status >= 500:
            return True
        name = type(exc).__name__.lower()
        return any(marker in name for marker in ("timeout", "connection", "ratelimit"))

    def extract_json(self, system_prompt: str, user_prompt: str) -> list[dict]:
        """发送 EIU 抽取请求，解析并返回 JSON 数组（解析失败抛出 LLMError）。"""
        content = self.chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
        try:
            return self._repair_json(content)
        except LLMError:
            logger.warning("EIU LLM JSON parsing failed output_chars=%s", len(content))
            raise

    @staticmethod
    def _repair_json(raw: str) -> list[dict]:
        """解析 LLM 输出为 JSON 数组；非标准 JSON 尝试修复（验收 F13）。

        修复顺序：直接解析 → 提取 ```json ... ``` 块 → 截取首个 [ 到末个 ]。
        全部失败则抛出 LLMError，由抽取器跳过该 Block 并记录。
        """
        if not raw or not raw.strip():
            raise LLMError("LLM 返回空内容")

        def _load(text: str) -> list[dict] | None:
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                return None
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict)]
            if isinstance(data, dict):
                for key in ("items", "eius", "results", "data"):
                    value = data.get(key)
                    if isinstance(value, list):
                        return [item for item in value if isinstance(item, dict)]
            return None

        parsed = _load(raw)
        if parsed is not None:
            return parsed

        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
        if match:
            parsed = _load(match.group(1).strip())
            if parsed is not None:
                return parsed

        start, end = raw.find("["), raw.rfind("]")
        if start != -1 and end > start:
            parsed = _load(raw[start : end + 1])
            if parsed is not None:
                return parsed

        raise LLMError("LLM 返回内容无法解析为 JSON 数组")
