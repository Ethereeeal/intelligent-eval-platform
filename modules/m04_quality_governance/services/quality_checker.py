"""m04 质量门禁：单题 5 项质量检查（README §2.2 校验流程核心）。

对单个 eval_case 执行：
  1. 组装原文上下文（EIU 陈述 + 证据原文）供问题相关性检查
  2. 一次 LLM 调用产出 5 项结论（README §2.1：#1–#5）
  3. 宽容解析并规整为 QualityReport（缺失项按 failed 处理，保证门禁严格）
"""
from __future__ import annotations

import json
import re
from typing import Any

from modules.m04_quality_governance.models import CheckItem, QualityReport
from modules.m04_quality_governance.services.llm_service import LLMService
from modules.m04_quality_governance.services.prompts import (
    CHECK_TYPES,
    build_quality_check_prompt,
)
from modules.shared.core.config import settings
from modules.shared.services.database import DatabaseService


class QualityChecker:
    def __init__(self) -> None:
        self.database = DatabaseService()
        self.llm = LLMService()

    # ------------------------------------------------------------------
    # 对外入口：单 case 检查
    # ------------------------------------------------------------------
    def check_case(self, case: dict[str, Any]) -> QualityReport:
        """对单个 eval_case 执行 5 项质量检查，返回报告（不落库）。"""
        evidence = self._parse_json_list(case.get("evidence"))
        source_context = self._resolve_source_context(case)

        prompt = build_quality_check_prompt(
            question=case["question"],
            gold_answer=case["gold_answer"],
            must_have_points=self._parse_json_list(case.get("must_have_points")),
            acceptable_answers=self._parse_json_list(case.get("acceptable_answers")),
            evidence=evidence,
            source_context=source_context,
        )
        response = self.llm.call(prompt, temperature=0.0, max_tokens=settings.llm_max_tokens)
        raw_checks = self._parse_checks(response)
        items = self._normalize_checks(raw_checks)
        return QualityReport(case_id=case["case_id"], checks=items)

    @staticmethod
    def _parse_json_list(value: Any) -> list[Any]:
        """兼容 DB 中以 JSON 文本存储的 list 字段（m03 落库为字符串）。"""
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, list) else []
            except (json.JSONDecodeError, TypeError):
                return []
        return []

    # ------------------------------------------------------------------
    # 原文上下文（问题相关性检查依据）
    # ------------------------------------------------------------------
    def _resolve_source_context(self, case: dict[str, Any]) -> str | None:
        """拼接 EIU 陈述 + 证据原文，作为问题相关性检查的原文依据。"""
        parts: list[str] = []

        eiu_id = case.get("eiu_id")
        if eiu_id is not None:
            eiu = self.database.get_eiu(eiu_id)
            if eiu:
                parts.append(
                    f"[EIU {eiu_id} · {eiu.get('eiu_type', '')}] {eiu.get('statement', '')}"
                )

        evidence = self._parse_json_list(case.get("evidence"))
        for binding in evidence:
            ev = binding.get("evidence") or {}
            original = ev.get("original_text")
            if original:
                parts.append(f"[原文 {ev.get('section_path', '未分类')}]: {original[:500]}")

        return "\n".join(parts) if parts else None

    # ------------------------------------------------------------------
    # LLM 结果解析与规整
    # ------------------------------------------------------------------
    def _parse_checks(self, response: str) -> list[dict[str, Any]]:
        """宽容解析：支持 {checks: [...]} 或直接数组 / 代码块围栏。"""
        text = response.strip()
        candidates: list[str] = [text]
        fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL)
        if fence_match:
            candidates.append(fence_match.group(1).strip())

        for candidate in candidates:
            try:
                data = json.loads(candidate)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(data, dict) and isinstance(data.get("checks"), list):
                return [d for d in data["checks"] if isinstance(d, dict)]
            if isinstance(data, list):
                return [d for d in data if isinstance(d, dict)]
        raise ValueError(f"无法解析质量检查结果 JSON: {response[:300]}")

    @staticmethod
    def _normalize_checks(raw: list[dict[str, Any]]) -> list[CheckItem]:
        """规整为 5 项固定顺序；缺失项按 failed 处理（门禁严格，不默认放行）。"""
        by_type: dict[str, dict[str, Any]] = {}
        for item in raw:
            check_type = str(item.get("check_type") or "").strip()
            if check_type in CHECK_TYPES:
                by_type[check_type] = item

        items: list[CheckItem] = []
        for check_type in CHECK_TYPES:
            item = by_type.get(check_type)
            if item is None:
                items.append(
                    CheckItem(
                        check_type=check_type,
                        passed=False,
                        reason="LLM 未返回该项检查结果",
                    )
                )
                continue
            passed = bool(item.get("passed"))
            reason = str(item.get("reason") or ("通过" if passed else "未给出失败原因"))
            items.append(CheckItem(check_type=check_type, passed=passed, reason=reason))
        return items
