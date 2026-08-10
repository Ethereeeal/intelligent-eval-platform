"""m03 评测集生成：内部数据记录（dataclass）。

真实持久化模型位于 modules/shared/services/database.py（EiuRow / EvalCaseRow），
此处仅定义服务层内部流转使用的轻量结构。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EiuRecord:
    """可出题信息单元（m02 产出，m03 输入）。"""

    eiu_id: int
    document_id: int
    block_id: int
    statement: str
    eiu_type: str
    content_priority: str
    weight: int
    constraints_json: dict | None = None
    evidence_blocks: list[int] = field(default_factory=list)
    is_questionable: bool = True
    exclusion_reason: str | None = None


@dataclass
class BlockEvidence:
    """单条原文证据（FR-PARSE-003 定位字段 + FR-QG-003 绑定）。"""

    document_id: int
    document_name: str
    section_path: str
    page_no: str | None
    block_id: int
    original_text: str
    start_offset: int | None = None
    end_offset: int | None = None


@dataclass
class GeneratedCase:
    """一次 LLM 生成产出的完整评测样本（按文档维度组织）。"""

    intent_id: str
    eiu_id: int | None
    document_id: int | None
    question: str
    question_type: str
    difficulty: str
    scope_type: str
    gold_answer: str
    must_have_points: list[str] = field(default_factory=list)
    acceptable_answers: list[str] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    content_priority: str = "P2"
    review_status: str = "candidate"
    is_unanswerable: bool = False
    statement_norm: str | None = None  # 方案 B 跨库复用匹配键
