from __future__ import annotations

import json
from typing import Any

from app.core.config import settings


class LLMService:
    def __init__(self) -> None:
        self.api_url = settings.llm_api_url
        self.api_key = settings.llm_api_key
        self.model = settings.llm_model

    def _build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def call(self, prompt: str, temperature: float = 0.0, max_tokens: int = 512) -> str:
        if not self.api_url:
            raise ValueError("LLM_API_URL 未配置，请在环境变量中设置")

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        import requests

        response = requests.post(self.api_url, headers=self._build_headers(), data=json.dumps(payload))
        response.raise_for_status()
        data = response.json()

        if isinstance(data, dict) and "output" in data:
            return data["output"]
        if isinstance(data, dict) and "choices" in data and data["choices"]:
            return data["choices"][0].get("message", {}).get("content", "")
        return json.dumps(data, ensure_ascii=False)
