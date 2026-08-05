"""M02 — EIU 数据类与常量。

ORM（eiu 表）定义在 modules/shared/services/database.py（EiuRow），
本文件的 dataclass 供服务层 / 测试内部使用，字段与表结构保持一致。
"""
from __future__ import annotations

from dataclasses import dataclass, field

# 10 种 EIU 类型（与 shared.database.EIU_TYPES 保持一致）
EIU_TYPES = {
    "definition",
    "rule",
    "threshold",
    "date",
    "formula",
    "process",
    "exception",
    "prohibition",
    "metric",
    "change",
}

# 优先级 → 权重（与 shared.database.PRIORITY_WEIGHT 保持一致）
PRIORITY_WEIGHT = {"P0": 5, "P1": 3, "P2": 1}

# review_status 取值
REVIEW_STATUS = ("candidate", "quality_verified", "blocked")


@dataclass
class EiuRecord:
    """一条可评测信息单元（Evaluable Information Unit）。"""

    eiu_id: int | None = None
    corpus_id: int | None = None
    block_id: int | None = None
    statement: str = ""
    eiu_type: str = "rule"
    content_priority: str = "P2"
    weight: int = 1
    constraints: dict | None = None
    evidence_blocks: list[int] = field(default_factory=list)
    is_questionable: bool = True
    exclusion_reason: str | None = None
    extraction_model: str | None = None
    extraction_confidence: float | None = None
    review_status: str = "candidate"
    created_at: str | None = None
