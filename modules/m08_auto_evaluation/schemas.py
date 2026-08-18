"""M08 — Agent 评测：请求 / 响应模型（BRD §9）。"""
from __future__ import annotations

from pydantic import BaseModel


class EvaluationRunRequest(BaseModel):
    """发起一次批量评测运行（组合作为输入）。"""

    composition_id: int
    name: str | None = None
    adapter: str = "mock"
    adapter_config: dict | None = None
