"""M08 — Agent 评测：请求 / 响应模型（BRD §9）。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class IntermediateEvalConfig(BaseModel):
    """运行级中间评测配置；节点可选，节点内指标固定。"""

    enabled: bool = False
    nodes: list[Literal["rewrite", "intent", "rag"]] = Field(default_factory=list)


class EvaluationRunRequest(BaseModel):
    """发起一次批量评测运行（组合作为输入）。"""

    composition_id: int
    name: str | None = None
    adapter: str = "mock"
    adapter_config: dict | None = None
    intermediate_eval: IntermediateEvalConfig = Field(default_factory=IntermediateEvalConfig)


class EvaluationExportRequest(BaseModel):
    """导出一次运行的全部结果，或指定的页面筛选结果。"""

    result_ids: list[int] | None = None


class ErrorBookUpdateRequest(BaseModel):
    """测试人员对异常项的人工处置，不覆盖原始评测结果。"""

    status: Literal["open", "processed", "ignored"]
    resolution_category: str | None = Field(default=None, max_length=64)
    resolution_note: str | None = Field(default=None, max_length=2000)


class EvaluationCaseRetryRequest(BaseModel):
    """单题复测时重新提交可用凭据，敏感配置不从历史运行中回读。"""

    adapter_config: dict | None = None
    analysis_threshold: float = Field(default=0.5, ge=0, le=1)


class ContextAnalysisRequest(BaseModel):
    """失败或不确定多轮样本的人工上下文分析。"""

    category: Literal[
        "memory_failure",
        "contradiction",
        "constraint_violation",
        "answer_error",
        "uncertain",
    ]
    note: str = Field(min_length=1, max_length=2000)


class AdapterTestRequest(BaseModel):
    """保存配置前使用一条问题验证目标智能体通路。"""

    adapter: str
    adapter_config: dict | None = None
    question: str = Field(min_length=1, max_length=2000)
