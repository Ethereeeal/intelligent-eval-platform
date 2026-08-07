"""m04 质量门禁：LLM 调用封装。

实现已统一收敛到 modules.shared.core.llm_client，本模块仅做兼容重导出，
保留 LLMService.call(prompt) 接口，避免大范围改动调用方。
"""
from __future__ import annotations

from modules.shared.core.llm_client import LLMError, call


class LLMService:
    """兼容别名：委托共享 LLM 客户端。"""

    def call(self, prompt: str, *, temperature: float = 0.0, max_tokens: int = 2048) -> str:
        return call(prompt, temperature=temperature, max_tokens=max_tokens)


__all__ = ["LLMService", "LLMError", "call"]
