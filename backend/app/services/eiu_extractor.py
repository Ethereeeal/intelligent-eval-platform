"""EIU extractor for business requirement documents.

Extracts test function points (EIU) from business requirement documents
without generating standard answers.  This is a lightweight pipeline compared
to the full document → Q&A evaluation set generation.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExtractedEIU:
    """A single extracted test function point."""
    section_path: str
    requirement_id: str | None
    statement: str
    eiu_type: str  # "functional_rule" | "business_rule" | "data_rule" | "interface_rule" | "nfr"
    content_priority: str  # "P0" | "P1" | "P2"
    weight: int = 1
    evidence_range: list[str] = field(default_factory=list)
    is_questionable: bool = True
    exclusion_reason: str | None = None
    extraction_confidence: float = 0.0


class EiuExtractor:
    """Extract EIUs from business requirement documents.

    Rules (see BRD FR-REQ2EIU-004):
    1. Functional points: "系统应/应支持/应提供/应实现..." → EIU
    2. Business rules: "如果...则...", "当...时...", "...不得...", "...必须..." → EIU
    3. Data rules: field definitions, format requirements, value ranges → EIU
    4. Interface rules: input/output params, error codes → EIU
    5. NFR: performance metrics, security requirements → EIU
    6. Exclusions: background descriptions, non-binding suggestions → not EIU

    Demo implementation: rule-based keyword matching.
    Production: LLM-based extraction with dual-channel verification.
    """

    # Keywords that suggest a functional requirement
    FUNCTIONAL_PATTERNS = [
        "系统应", "系统应当", "系统必须", "平台应", "平台应当",
        "应支持", "应提供", "应实现", "应具备", "应允许",
        "需要支持", "需要提供", "需要实现",
    ]

    # Keywords that suggest a business rule
    BUSINESS_RULE_PATTERNS = [
        "如果", "则", "当", "时", "不得", "禁止", "必须",
        "不得大于", "不得小于", "不得超过", "不应超过",
        "最多", "最少", "至少", "原则上",
    ]

    # Keywords that suggest a data rule
    DATA_RULE_PATTERNS = [
        "字段", "格式为", "取值范围", "长度", "类型为",
        "不超过", "不少于", "只能包含", "必须包含",
    ]

    # Keywords that suggest an NFR
    NFR_PATTERNS = [
        "响应时间", "并发", "TPS", "QPS", "可用性",
        "99.", "SLA", "吞吐量", "容量",
    ]

    # Keywords that indicate non-substantive content (should be excluded)
    EXCLUSION_PATTERNS = [
        "背景", "概述", "总体目标", "项目目标",
        "参考", "术语表", "文档约定",
    ]

    def extract_from_text(self, text: str, section_path: str = "") -> list[ExtractedEIU]:
        """Extract EIUs from plain text content.

        Args:
            text: The text content of a requirement document section.
            section_path: The section path for provenance tracking.

        Returns:
            List of extracted EIUs.
        """
        sentences = self._split_sentences(text)
        results: list[ExtractedEIU] = []

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence or len(sentence) < 5:
                continue

            # Check exclusion first
            if self._is_excluded(sentence):
                continue

            eiu_type, priority = self._classify(sentence)
            if eiu_type is None:
                continue

            results.append(
                ExtractedEIU(
                    section_path=section_path,
                    requirement_id=None,  # can be parsed from structured docs
                    statement=sentence,
                    eiu_type=eiu_type,
                    content_priority=priority,
                    weight=self._default_weight(priority),
                    extraction_confidence=0.85,  # rule-based default
                )
            )

        return results

    def _classify(self, sentence: str) -> tuple[str | None, str]:
        """Classify a sentence into EIU type and priority.

        Returns (eiu_type, priority) or (None, "") if not a valid EIU.
        """
        # Check functional patterns first
        if any(p in sentence for p in self.FUNCTIONAL_PATTERNS):
            # Determine priority based on keywords
            if any(kw in sentence for kw in ["安全", "合规", "禁止", "必须", "不得", "认证", "授权"]):
                return ("functional_rule", "P0")
            return ("functional_rule", "P1")

        # Check business rules
        if any(p in sentence for p in self.BUSINESS_RULE_PATTERNS):
            if any(kw in sentence for kw in ["安全", "合规", "禁止", "必须", "不得", "例外"]):
                return ("business_rule", "P0")
            return ("business_rule", "P1")

        # Check data rules
        if any(p in sentence for p in self.DATA_RULE_PATTERNS):
            return ("data_rule", "P1")

        # Check NFR
        if any(p in sentence for p in self.NFR_PATTERNS):
            return ("nfr", "P1")

        return (None, "")

    def _is_excluded(self, sentence: str) -> bool:
        """Check if a sentence should be excluded from EIU extraction."""
        return any(p in sentence for p in self.EXCLUSION_PATTERNS)

    @staticmethod
    def _default_weight(priority: str) -> int:
        """Default weight by content priority."""
        return {"P0": 5, "P1": 3, "P2": 1}.get(priority, 1)

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """Split text into sentences using Chinese punctuation."""
        import re
        # Split on Chinese/English sentence-ending punctuation
        parts = re.split(r'[。！？；\n;!?]+', text)
        return [p.strip() for p in parts if p.strip()]
