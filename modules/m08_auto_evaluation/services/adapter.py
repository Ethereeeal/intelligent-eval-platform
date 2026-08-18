"""待测系统标准适配器（BRD §9.1 FR-RUN-001）。

- mock：本地示例回答，无外部依赖（Demo / 离线演示）；
- openai_compatible：OpenAI 兼容问答接口（question / 多轮 turns）。

统一返回结构：
  {"answer": str|None, "turn_outputs": list|None, "retrieved": list|None,
   "context": str|None, "usage": {"time_ms","tokens","cost"}, "error": str|None}

retrieved 为 None 表示待测系统未返回检索轨迹 → 运行报告标记"不可诊断检索层"。
"""
from __future__ import annotations

import time

from modules.shared.core.config import settings


class AdapterError(RuntimeError):
    """适配器调用失败。"""


class BaseAdapter:
    name = "base"

    def run_single(
        self,
        question: str,
        *,
        gold_answer: str | None = None,
        extra: dict | None = None,
    ) -> dict:
        raise NotImplementedError

    def run_multi(
        self,
        turns: list[dict],
        *,
        gold_answer: str | None = None,
        extra: dict | None = None,
    ) -> dict:
        raise NotImplementedError


class MockAdapter(BaseAdapter):
    """示例适配器：返回固定回答，无检索轨迹（retrieved=None → 不可诊断检索层）。"""

    name = "mock"

    def __init__(self, config: dict | None = None) -> None:
        self.reply = str((config or {}).get("reply") or "（mock 适配器：示例回答，未接入真实待测系统）")

    def _base(self) -> dict:
        return {
            "retrieved": None,
            "context": None,
            "usage": {"time_ms": 1, "tokens": 0, "cost": 0.0},
            "error": None,
        }

    def run_single(
        self,
        question: str,
        *,
        gold_answer: str | None = None,
        extra: dict | None = None,
    ) -> dict:
        return {"answer": self.reply, "turn_outputs": None, **self._base()}

    def run_multi(
        self,
        turns: list[dict],
        *,
        gold_answer: str | None = None,
        extra: dict | None = None,
    ) -> dict:
        return {
            "answer": self.reply,
            "turn_outputs": [self.reply for _ in turns],
            **self._base(),
        }


class OpenAiCompatibleAdapter(BaseAdapter):
    """OpenAI 兼容问答适配器（question / 多轮 turns）。"""

    name = "openai_compatible"

    def __init__(self, config: dict | None = None) -> None:
        cfg = config or {}
        self.api_base = cfg.get("api_base") or settings.llm_api_base
        self.api_key = cfg.get("api_key") or settings.llm_api_key
        self.model = cfg.get("model") or settings.llm_model
        self.system_prompt = cfg.get("system_prompt") or (
            "你是业务问答助手，请基于给定材料回答问题；没有材料时明确说明无法回答，不要编造。"
        )
        self._client = None
        if self.api_key and not self.api_key.startswith("sk-xxx"):
            try:
                import openai

                self._client = openai.OpenAI(
                    api_key=self.api_key,
                    base_url=self.api_base,
                    timeout=120,
                    max_retries=0,
                )
            except ImportError:
                self._client = None

    def _chat(self, messages: list[dict]) -> str:
        if self._client is None:
            raise AdapterError(
                "openai_compatible 适配器不可用：缺少 openai 库或 API Key 未配置；请改用 mock 适配器"
            )
        start = time.time()
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": self.system_prompt}, *messages],
            temperature=0.1,
        )
        elapsed_ms = int((time.time() - start) * 1000)
        content = (response.choices[0].message.content or "") if response.choices else ""
        usage = response.usage
        tokens = (usage.total_tokens if usage else 0) or 0
        return content, elapsed_ms, tokens

    def run_single(
        self,
        question: str,
        *,
        gold_answer: str | None = None,
        extra: dict | None = None,
    ) -> dict:
        try:
            content, elapsed, tokens = self._chat([{"role": "user", "content": question}])
            return {
                "answer": content,
                "turn_outputs": None,
                "retrieved": None,
                "context": None,
                "usage": {"time_ms": elapsed, "tokens": tokens, "cost": 0.0},
                "error": None,
            }
        except AdapterError:
            raise
        except Exception as exc:  # noqa: BLE001
            return {
                "answer": None,
                "turn_outputs": None,
                "retrieved": None,
                "context": None,
                "usage": {"time_ms": 0, "tokens": 0, "cost": 0.0},
                "error": str(exc),
            }

    def run_multi(
        self,
        turns: list[dict],
        *,
        gold_answer: str | None = None,
        extra: dict | None = None,
    ) -> dict:
        try:
            messages: list[dict] = []
            outputs: list[str] = []
            for index, turn in enumerate(turns):
                if not isinstance(turn, dict):
                    continue
                messages.append({"role": "user", "content": str(turn.get("q") or "")})
                is_last = index == len(turns) - 1
                if not is_last and turn.get("key_turn") is None and turn.get("a"):
                    # 中间非关键轮：注入已给历史答案（memory/coherence 验证依赖前置信息）；
                    # 关键轮（key_turn）与最终轮必须由模型回答
                    messages.append({"role": "assistant", "content": str(turn.get("a"))})
                else:
                    content, elapsed, tokens = self._chat(messages)
                    outputs.append(content)
                    messages.append({"role": "assistant", "content": content})
            final = outputs[-1] if outputs else ""
            return {
                "answer": final,
                "turn_outputs": outputs,
                "retrieved": None,
                "context": None,
                "usage": {"time_ms": 0, "tokens": 0, "cost": 0.0},
                "error": None,
            }
        except AdapterError:
            raise
        except Exception as exc:  # noqa: BLE001
            return {
                "answer": None,
                "turn_outputs": None,
                "retrieved": None,
                "context": None,
                "usage": {"time_ms": 0, "tokens": 0, "cost": 0.0},
                "error": str(exc),
            }


ADAPTER_REGISTRY: dict[str, type[BaseAdapter]] = {
    "mock": MockAdapter,
    "openai_compatible": OpenAiCompatibleAdapter,
}


def get_adapter(name: str, config: dict | None = None) -> BaseAdapter:
    """按名称实例化适配器（注册表）。"""
    adapter_cls = ADAPTER_REGISTRY.get(name)
    if adapter_cls is None:
        raise AdapterError(f"未知适配器: {name}（可用: {sorted(ADAPTER_REGISTRY)}）")
    return adapter_cls(config)
