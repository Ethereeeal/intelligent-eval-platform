"""m03 评测集生成：LLM 调用封装。

对接 OpenAI 兼容接口（/chat/completions），配置项从
modules.shared.core.config.settings 读取，通过环境变量注入：
  LLM_API_URL（原项目命名，如 https://api.deepseek.com）
  LLM_API_BASE（intelligent 项目命名，OpenAI 兼容）
  LLM_API_KEY / LLM_MODEL

两者兼容：优先 LLM_API_URL，未配置时回退 LLM_API_BASE。

LLM_API_URL 支持裸域名（如 https://api.deepseek.com），会自动补全
/chat/completions 路径；也兼容已带完整路径的配置。
"""
from __future__ import annotations

import json
from typing import Any

from modules.shared.core.config import settings


class LLMService:
    def __init__(self) -> None:
        # 兼容两种配置命名：LLM_API_URL（原项目）/ LLM_API_BASE（intelligent）
        self.api_url = (
            getattr(settings, "llm_api_url", None)
            or getattr(settings, "llm_api_base", None)
            or ""
        )
        self.api_key = getattr(settings, "llm_api_key", "") or ""
        self.model = getattr(settings, "llm_model", "") or ""

    def _build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _completions_url(self) -> str:
        url = self.api_url.rstrip("/")
        if url.endswith("/chat/completions"):
            return url
        if url.endswith("/v1"):
            return f"{url}/chat/completions"
        return f"{url}/chat/completions"

    def call(
        self,
        prompt: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> str:
        """调用 LLM 并返回文本。未配置 LLM_API_URL 时抛 ValueError。"""
        if not self.api_url:
            raise ValueError(
                "LLM_API_URL 未配置。请设置环境变量 LLM_API_URL / LLM_API_KEY / LLM_MODEL"
            )

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        import requests

        response = requests.post(
            self._completions_url(),
            headers=self._build_headers(),
            data=json.dumps(payload),
        )
        response.raise_for_status()
        data = response.json()

        # 兼容两种常见返回形态
        if isinstance(data, dict) and "output" in data:
            output = data["output"]
            return output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
        if isinstance(data, dict) and "choices" in data and data["choices"]:
            return data["choices"][0].get("message", {}).get("content", "")
        return json.dumps(data, ensure_ascii=False)
