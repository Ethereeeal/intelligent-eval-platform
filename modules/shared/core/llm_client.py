"""共享 LLM 调用客户端（OpenAI 兼容 /chat/completions）。

集中管理 LLM 网络调用，避免各模块重复实现 requests 逻辑（原 m03/m04 各维护一份
几乎相同的 LLMService）。统一提供：
- 超时控制（避免请求无限挂起）
- 失败重试（网络抖动自动恢复）
- 结构化日志（记录调用耗时与失败原因，禁止裸 print）
- 异常统一包装为 LLMError

配置项（来自 modules.shared.core.config.settings）：
  LLM_API_URL  / LLM_API_BASE：兼容两种命名，OpenAI 兼容端点
  LLM_API_KEY / LLM_MODEL
"""
from __future__ import annotations

import json
import time
from typing import Any

import requests

from modules.shared.core.config import settings
from modules.shared.core.logging_config import get_logger

logger = get_logger(__name__)

# 调用超时（秒）：读/连接各 30s，避免请求无限挂起
# 推理模型（如 deepseek-v4-flash）生成长文耗时较长，读超时放宽到 600s
_REQUEST_TIMEOUT = (30, 600)
# 失败重试次数（不含首次）
_MAX_RETRIES = 2
# 重试间隔（秒）
_RETRY_BACKOFF = 3

# 兼容两种配置命名：LLM_API_URL（原项目）/ LLM_API_BASE（intelligent）
_API_URL = getattr(settings, "llm_api_url", None) or getattr(settings, "llm_api_base", None) or ""
_API_KEY = getattr(settings, "llm_api_key", "") or ""
_API_MODEL = getattr(settings, "llm_model", "") or ""


class LLMError(RuntimeError):
    """LLM 调用或解析失败。"""


def _completions_url() -> str:
    url = _API_URL.rstrip("/")
    if url.endswith("/chat/completions"):
        return url
    if url.endswith("/v1"):
        return f"{url}/chat/completions"
    return f"{url}/chat/completions"


def call(
    prompt: str,
    *,
    temperature: float = 0.0,
    max_tokens: int = 2048,
) -> str:
    """调用 LLM 并返回文本。

    未配置 LLM_API_URL 时抛 ValueError；网络错误按 _MAX_RETRIES 重试；
    非 2xx 或非预期返回结构抛 LLMError。
    """
    if not _API_URL:
        raise ValueError("LLM_API_URL 未配置。请设置 LLM_API_URL / LLM_API_KEY / LLM_MODEL")

    headers = {"Content-Type": "application/json"}
    if _API_KEY:
        headers["Authorization"] = f"Bearer {_API_KEY}"

    payload: dict[str, Any] = {
        "model": _API_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    url = _completions_url()
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            logger.debug("LLM call attempt=%d model=%s url=%s", attempt, _API_MODEL, url)
            start = time.monotonic()
            response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=_REQUEST_TIMEOUT)
            elapsed = time.monotonic() - start
            if response.status_code != 200:
                logger.warning("LLM call http=%d elapsed=%.2fs", response.status_code, elapsed)
                response.raise_for_status()
            logger.debug("LLM call ok elapsed=%.2fs", elapsed)
            parsed = _parse_response(response.json())
            if not parsed or not parsed.strip():
                logger.warning(
                    "LLM 返回空内容 model=%s elapsed=%.2fs raw=%s",
                    _API_MODEL,
                    elapsed,
                    response.text[:500],
                )
            return parsed
        except requests.RequestException as exc:
            last_exc = exc
            logger.warning("LLM call failed attempt=%d: %s", attempt, exc)
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_BACKOFF)

    raise LLMError(f"LLM 调用失败（已重试 {_MAX_RETRIES} 次）: {last_exc}")


def _parse_response(data: Any) -> str:
    """兼容主流返回形态：DashScope(output) / OpenAI(choices) / 兜底 JSON。"""
    if not isinstance(data, dict):
        return json.dumps(data, ensure_ascii=False)
    if "output" in data:
        output = data["output"]
        return output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
    if "choices" in data and data["choices"]:
        return data["choices"][0].get("message", {}).get("content", "")
    return json.dumps(data, ensure_ascii=False)
