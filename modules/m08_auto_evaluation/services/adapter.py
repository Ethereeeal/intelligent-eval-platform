"""待测系统标准适配器（BRD §9.1 FR-RUN-001）。

- mock：本地示例回答，无外部依赖（Demo / 离线演示）；
- openai_compatible：OpenAI 兼容问答接口（question / 多轮 turns）。

统一返回结构：
  {"answer": str|None, "turn_outputs": list|None, "retrieved": list|None,
   "context": str|None, "usage": {"time_ms","tokens","cost"}, "error": str|None}

retrieved 为 None 表示待测系统未返回检索轨迹 → 运行报告标记"不可诊断检索层"。
"""
from __future__ import annotations

import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

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
            total_elapsed_ms = 0
            total_tokens = 0
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
                    total_elapsed_ms += elapsed
                    total_tokens += tokens
                    outputs.append(content)
                    messages.append({"role": "assistant", "content": content})
            final = outputs[-1] if outputs else ""
            return {
                "answer": final,
                "turn_outputs": outputs,
                "retrieved": None,
                "context": None,
                "usage": {
                    "time_ms": total_elapsed_ms,
                    "tokens": total_tokens,
                    "cost": 0.0,
                },
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


class HttpAdapter(BaseAdapter):
    """通用 HTTP 问答适配器：以 {{question}} 注入请求体并从 JSON 响应提取答案。"""

    name = "http"

    def __init__(self, config: dict | None = None) -> None:
        cfg = config or {}
        self.url = str(cfg.get("url") or "").strip()
        self.method = str(cfg.get("method") or "POST").upper()
        self.headers = cfg.get("headers") or {}
        self.body_template = cfg.get("body_template") or '{"question":"{{question}}"}'
        self.answer_path = str(cfg.get("answer_path") or "answer").strip()
        self.observation_paths = cfg.get("observation_paths") or {}
        self.timeout = min(max(int(cfg.get("timeout_seconds") or 60), 1), 120)
        if not self.url.startswith(("http://", "https://")):
            raise AdapterError("通用 HTTP 请求地址必须以 http:// 或 https:// 开头")
        if self.method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            raise AdapterError("不支持的 HTTP 请求方法")
        if not isinstance(self.headers, dict):
            raise AdapterError("请求头必须为键值对象")
        if not isinstance(self.observation_paths, dict) or not all(
            isinstance(label, str) and isinstance(path, str)
            for label, path in self.observation_paths.items()
        ):
            raise AdapterError("关键返回字段必须是“显示名: 字段路径”的 JSON 对象")

    @staticmethod
    def _resolve_value(payload: object, path: str) -> Any:
        value = payload
        for key in path.removeprefix("$").strip(".").split("."):
            if key:
                if isinstance(value, dict) and key in value:
                    value = value[key]
                elif isinstance(value, list) and key.isdigit() and int(key) < len(value):
                    value = value[int(key)]
                else:
                    raise AdapterError(f"响应中未找到字段：{path}")
        return value

    @classmethod
    def _resolve_path(cls, payload: object, path: str) -> str:
        value = cls._resolve_value(payload, path)
        return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value or "")

    def _observations(self, payload: object) -> dict | None:
        """保留答案以外的可观察返回字段；显式路径可补充嵌套的重要节点。"""
        observations: dict[str, Any] = {}
        if isinstance(payload, dict):
            answer_root = self.answer_path.removeprefix("$").strip(".").split(".")[0]
            observations.update({key: value for key, value in payload.items() if key != answer_root})
        for label, path in self.observation_paths.items():
            observations[label] = self._resolve_value(payload, path)
        return observations or None

    def _call(self, question: str) -> dict:
        headers = {str(k): str(v) for k, v in self.headers.items() if str(k).strip()}
        url, data = self.url, None
        if self.method == "GET":
            url += ("&" if "?" in url else "?") + "question=" + quote(question)
        else:
            data = str(self.body_template).replace("{{question}}", question).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")
        started = time.time()
        try:
            with urlopen(Request(url, data=data, headers=headers, method=self.method), timeout=self.timeout) as response:  # nosec B310: configured integration endpoint
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise AdapterError(f"目标接口返回 HTTP {exc.code}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise AdapterError(f"目标接口调用失败：{exc}") from exc
        return {
            "answer": self._resolve_path(payload, self.answer_path),
            "turn_outputs": None,
            "retrieved": None,
            "agent_observations": self._observations(payload),
            "context": None,
            "usage": {"time_ms": int((time.time() - started) * 1000), "tokens": 0, "cost": 0.0},
            "error": None,
        }

    def run_single(self, question: str, *, gold_answer: str | None = None, extra: dict | None = None) -> dict:
        try:
            return self._call(question)
        except AdapterError as exc:
            return {"answer": None, "turn_outputs": None, "retrieved": None, "context": None,
                    "usage": {"time_ms": 0, "tokens": 0, "cost": 0.0}, "error": str(exc)}

    def run_multi(self, turns: list[dict], *, gold_answer: str | None = None, extra: dict | None = None) -> dict:
        outputs = []
        last_observations = None
        for turn in turns:
            result = self.run_single(str((turn or {}).get("q") or ""))
            if result.get("error"):
                return result
            outputs.append(result["answer"])
            last_observations = result.get("agent_observations")
        return {"answer": outputs[-1] if outputs else "", "turn_outputs": outputs, "retrieved": None,
                "agent_observations": last_observations, "context": None,
                "usage": {"time_ms": 0, "tokens": 0, "cost": 0.0}, "error": None}


ADAPTER_REGISTRY: dict[str, type[BaseAdapter]] = {
    "mock": MockAdapter,
    "openai_compatible": OpenAiCompatibleAdapter,
    "http": HttpAdapter,
}


def get_adapter(name: str, config: dict | None = None) -> BaseAdapter:
    """按名称实例化适配器（注册表）。"""
    adapter_cls = ADAPTER_REGISTRY.get(name)
    if adapter_cls is None:
        raise AdapterError(f"未知适配器: {name}（可用: {sorted(ADAPTER_REGISTRY)}）")
    return adapter_cls(config)
