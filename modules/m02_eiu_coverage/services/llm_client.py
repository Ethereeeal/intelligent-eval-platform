"""LLM 客户端（OpenAI 兼容 API）。

- 使用 openai 库，兼容千问 / DeepSeek / vLLM 等 OpenAI 兼容端点（SPEC §5.2）
- 网络错误自动重试 2 次（共 3 次），间隔 3s，超时 120s（验收 F12）
- 返回内容解析为 JSON 数组，非标准 JSON 尝试修复（验收 F13）
- 未安装 openai 库，或 LLM_API_KEY 为占位符 "sk-xxx" 时进入 offline 模式：
  由 eiu_extractor 使用确定性规则抽取，保证离线 / 无 API Key 环境可演示。
"""
from __future__ import annotations

import json
import re
import time

from modules.shared.core.config import settings


class LLMError(RuntimeError):
    """LLM 调用 / 解析失败。"""


class LLMClient:
    def __init__(self) -> None:
        self.api_base = settings.llm_api_base
        self.api_key = settings.llm_api_key
        self.model = settings.llm_model
        self.temperature = settings.llm_temperature
        self.max_tokens = settings.llm_max_tokens

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
            # max_retries=0：重试逻辑由本类 chat() 统一控制（初始 1 次 + 重试 2 次）
            self._client = self._openai.OpenAI(
                api_key=self.api_key,
                base_url=self.api_base,
                timeout=120,
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
        """发送聊天请求，返回文本响应。网络错误重试 2 次，间隔 3s。"""
        if self.use_offline:
            raise LLMError("LLM 未配置（缺 openai 库或 API Key 为占位符），无法调用 chat()")
        if self._client is None:
            raise LLMError("LLM 客户端未初始化")

        last_exc: Exception | None = None
        for attempt in range(3):  # 初始 1 次 + 重试 2 次
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
                return content
            except Exception as exc:  # noqa: BLE001 — 网络 / 超时 / 上游错误统一重试
                last_exc = exc
                if attempt < 2:
                    time.sleep(3)
        raise LLMError(f"LLM 调用失败（已重试 2 次）: {last_exc}")

    def extract_json(self, system_prompt: str, user_prompt: str) -> list[dict]:
        """发送 EIU 抽取请求，解析并返回 JSON 数组（解析失败抛出 LLMError）。"""
        content = self.chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
        return self._repair_json(content)

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
