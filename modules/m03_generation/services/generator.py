"""m03 评测集生成：单 EIU 题目生成器。

流程（README §2.1）：
  1. 获取 EIU 原文证据 Block（含章节路径 + 页码）
  2. 获取相邻 Block 上下文（前 1 后 1）
  3. 一次 LLM 生成调用：同时产出 题目 + 标准答案 + 证据绑定
  4. 难度初判（LLM 输出 + 单段题 L3 降级复查，FR-DIFF-001/002）
  5. 将结果写入 eval_case 表，绑定 eiu_id
"""
from __future__ import annotations

import json
import re
from typing import Any

from modules.m03_generation.models import BlockEvidence, GeneratedCase
from modules.m03_generation.services.llm_service import LLMService
from modules.m03_generation.services.prompts import (
    CONTEXT_WINDOW,
    EIU_TYPE_TO_QUESTION_TYPE,
    MAX_CONTEXT_BLOCKS,
    build_qa_prompt,
)
from modules.shared.core.config import settings
from modules.shared.core.logging_config import get_logger
from modules.shared.services.database import (
    DatabaseService,
    normalize_statement,
)

logger = get_logger(__name__)


class CaseGenerator:
    def __init__(self) -> None:
        self.database = DatabaseService()
        self.llm = LLMService()

    # ------------------------------------------------------------------
    # 对外入口：单 EIU 生成一道题
    # ------------------------------------------------------------------
    def generate_for_eiu(
        self,
        eiu: dict[str, Any],
        *,
        angle: str = "primary",
        block: dict[str, Any] | None = None,
    ) -> GeneratedCase:
        """基于单个 EIU 生成一条规范评测样本（题目+答案+证据绑定）。

        eiu: 共享库 eiu 表记录（dict）。
        block: 源证据 Block；不传时自动从数据库按 evidence_blocks[0] 解析。
        """
        if not eiu.get("is_questionable", True):
            raise ValueError(f"EIU {eiu['eiu_id']} 不可出题：{eiu.get('exclusion_reason')}")

        # 1. 定位原文证据 Block 与动态筛选的上下文
        document_blocks = self.database.get_document_blocks(eiu["document_id"])
        block = block or self._resolve_source_block(eiu, blocks=document_blocks)
        context = self._resolve_context(eiu, block, blocks=document_blocks)
        document = self.database.get_document(eiu["document_id"]) or {}

        # 2. 题型映射（EIU 类型 → 题目类型）
        question_type = EIU_TYPE_TO_QUESTION_TYPE.get(
            eiu.get("eiu_type", ""), "rule"
        )

        # 3. 一次 LLM 调用：题目 + 答案 + 证据绑定
        prompt = build_qa_prompt(
            statement=eiu["statement"],
            eiu_type=eiu.get("eiu_type", "rule"),
            question_type=question_type,
            angle=angle,
            context=context,
            block_text=block.get("block_text", ""),
            section_path=block.get("section_path", "未分类"),
            page_no=block.get("page_no"),
            constraints=eiu.get("constraints_json"),
        )
        raw = self._call_and_parse(prompt)
        raw = self._validate_generation_output(
            raw,
            expected_question_type=question_type,
            statement=eiu["statement"],
        )

        if raw.get("is_unanswerable"):
            # README §2.3：原文证据不足以支撑规范答案时，不伪造答案、不落库
            raise ValueError(
                f"EIU {eiu['eiu_id']} 无法生成规范答案（is_unanswerable=true）："
                f"{raw.get('gold_answer', '原文证据不足')}"
            )

        # 4. 难度写死（#8）：由 EIU 类型/优先级规则映射，不依赖 LLM 自由裁量
        #    单段题不做 L3（README §5.1：L3 需跨段多跳），统一 ≤ L2
        difficulty = self._rule_difficulty(eiu.get("eiu_type", "rule"), eiu.get("content_priority", "P2"))

        # 5. 证据绑定写死（#9）：直接绑定生成该 EIU 的源 Block，不依赖 LLM 定位
        evidence = self._build_evidence_bindings(
            raw_evidence=raw.get("evidence_bindings", []),
            block=block,
            document=document,
            fallback_points=raw.get("must_have_points", [eiu["statement"]]),
            valid_blocks=document_blocks,
        )

        case = GeneratedCase(
            intent_id=f"intent_{eiu['eiu_id']}_{angle}",
            eiu_id=eiu["eiu_id"],
            document_id=eiu["document_id"],
            question=raw.get("question") or "",
            question_type=raw.get("question_type") or question_type,
            difficulty=difficulty,
            scope_type="single_segment",
            gold_answer=raw.get("gold_answer") or eiu["statement"],
            must_have_points=raw.get("must_have_points") or [eiu["statement"]],
            acceptable_answers=raw.get("acceptable_answers") or [],
            evidence=evidence,
            content_priority=eiu.get("content_priority", "P2"),
            statement_norm=normalize_statement(eiu.get("statement", "")),
        )
        if not case.question:
            raise ValueError(f"EIU {eiu['eiu_id']} 生成结果缺少 question 字段")
        return case

    def save_case(self, case: GeneratedCase) -> dict:
        """将 GeneratedCase 落库，返回生成的评测样本记录。"""
        return self.database.save_generated_case(
            intent_id=case.intent_id,
            eiu_id=case.eiu_id,
            document_id=case.document_id,
            question=case.question,
            question_type=case.question_type,
            difficulty=case.difficulty,
            scope_type=case.scope_type,
            gold_answer=case.gold_answer,
            must_have_points=case.must_have_points,
            acceptable_answers=case.acceptable_answers,
            evidence=case.evidence,
            content_priority=case.content_priority,
            review_status=case.review_status,
            statement_norm=case.statement_norm,
        )

    # ------------------------------------------------------------------
    # 原文定位与上下文
    # ------------------------------------------------------------------
    def _resolve_source_block(
        self, eiu: dict[str, Any], *, blocks: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        """从 EIU 的 evidence_blocks 中解析源 Block；缺省回退到 block_id。"""
        blocks = blocks if blocks is not None else self.database.get_document_blocks(eiu["document_id"])
        by_id = {b["block_id"]: b for b in blocks}
        evidence_ids = eiu.get("evidence_blocks") or [eiu.get("block_id")]
        for block_id in evidence_ids:
            if block_id in by_id:
                return by_id[block_id]
        raise ValueError(f"EIU {eiu['eiu_id']} 的证据 Block 未找到: {evidence_ids}")

    def _resolve_context(
        self,
        eiu: dict[str, Any],
        block: dict[str, Any],
        *,
        blocks: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """筛选上下文：仅用位置窗口（源块前后各 CONTEXT_WINDOW 个相邻块）。

        P0 改造：移除块向量语义召回（_build_document_index）。理由：
          - 单 EIU 出题只需「源块 + 相邻块」处理术语延续/指代，无需语义相近但
            不相邻的块（会引入干扰证据，且块向量层属冗余）。
          - 跨块题将走 EIU 向量 + 类型关系（后续），不在块层做。
        """
        document_id = eiu["document_id"]
        block_id = block["block_id"]
        blocks = blocks if blocks is not None else self.database.get_document_blocks(document_id)
        by_id = {b["block_id"]: b for b in blocks}
        ordered = sorted(blocks, key=lambda b: b.get("block_id") or 0)

        pos_index = next(
            (i for i, b in enumerate(ordered) if b["block_id"] == block_id), None
        )
        neighbor_ids: set[int] = set()
        if pos_index is not None:
            for i in range(
                max(0, pos_index - CONTEXT_WINDOW),
                min(len(ordered), pos_index + CONTEXT_WINDOW + 1),
            ):
                if ordered[i]["block_id"] != block_id:
                    neighbor_ids.add(ordered[i]["block_id"])

        context_blocks = []
        for nid in list(neighbor_ids)[:MAX_CONTEXT_BLOCKS]:
            blk = by_id.get(nid)
            if blk:
                context_blocks.append(blk)
        return context_blocks

    # ------------------------------------------------------------------
    # LLM 调用与解析
    # ------------------------------------------------------------------
    def _call_and_parse(self, prompt: str) -> dict[str, Any]:
        response = self.llm.call(prompt, temperature=0.0, max_tokens=settings.llm_max_tokens)
        data = self._parse_llm_json(response)
        if not isinstance(data, dict):
            raise ValueError(f"LLM 返回不是 JSON 对象: {response[:200]}")
        return data

    @staticmethod
    def _parse_llm_json(response: str) -> dict[str, Any]:
        """宽容解析：优先整体 JSON，失败则剥离 ```json 代码块再解析。"""
        text = response.strip()
        for candidate in (text, _strip_code_fence(text)):
            try:
                data = json.loads(candidate)
                if isinstance(data, dict):
                    return data
            except (json.JSONDecodeError, TypeError):
                continue
        raise ValueError(f"无法解析 LLM 返回的 JSON: {response[:300]}")

    @staticmethod
    def _validate_generation_output(
        raw: dict[str, Any], *, expected_question_type: str, statement: str
    ) -> dict[str, Any]:
        """规范化 LLM 字段，阻止错误结构进入 eval_case。"""
        question = raw.get("question")
        if not isinstance(question, str) or not question.strip():
            raise ValueError("LLM 返回缺少有效 question")
        if len(question) > 2000:
            raise ValueError("question 超过 2000 字")

        gold_answer = raw.get("gold_answer")
        if not isinstance(gold_answer, str) or not gold_answer.strip():
            gold_answer = statement
        if len(gold_answer) > 10000:
            raise ValueError("gold_answer 超过 10000 字")

        def string_list(value: Any) -> list[str]:
            if not isinstance(value, list):
                return []
            return [item.strip() for item in value if isinstance(item, str) and item.strip()]

        must_have_points = string_list(raw.get("must_have_points")) or [statement]
        acceptable_answers = string_list(raw.get("acceptable_answers"))
        evidence_bindings = raw.get("evidence_bindings")
        if not isinstance(evidence_bindings, list):
            evidence_bindings = []

        question_type = raw.get("question_type")
        if question_type != expected_question_type:
            question_type = expected_question_type

        return {
            **raw,
            "question": question.strip(),
            "question_type": question_type,
            "gold_answer": gold_answer.strip(),
            "must_have_points": must_have_points,
            "acceptable_answers": acceptable_answers,
            "evidence_bindings": evidence_bindings,
            "is_unanswerable": raw.get("is_unanswerable") is True,
        }

    # ------------------------------------------------------------------
    # 证据绑定（FR-QG-003）
    # ------------------------------------------------------------------
    @staticmethod
    def _build_evidence_bindings(
        *,
        raw_evidence: list[Any],
        block: dict[str, Any],
        document: dict[str, Any],
        fallback_points: list[str],
        valid_blocks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """把 must_have_point 与底层原文证据绑定。

        LLM 已给出 evidence 定位时优先采用；缺字段则用源 Block 定位兜底。
        """
        source = BlockEvidence(
            document_id=document.get("document_id") or 0,
            document_name=document.get("file_name") or "",
            section_path=block.get("section_path", "未分类"),
            page_no=block.get("page_no"),
            block_id=block.get("block_id"),
            original_text=(block.get("block_text") or "")[:500],
            start_offset=block.get("start_offset"),
            end_offset=block.get("end_offset"),
        )
        block_by_id = {item.get("block_id"): item for item in valid_blocks}
        bindings: list[dict[str, Any]] = []

        if isinstance(raw_evidence, list):
            for item in raw_evidence:
                if not isinstance(item, dict):
                    continue
                point = item.get("must_have_point")
                ev = item.get("evidence") or {}
                evidence_block_id = ev.get("block_id")
                candidate_block = block_by_id.get(evidence_block_id)
                original_text = ev.get("original_text")
                if (
                    not isinstance(point, str)
                    or not point.strip()
                    or not isinstance(original_text, str)
                    or not original_text
                    or candidate_block is None
                    or original_text not in (candidate_block.get("block_text") or "")
                ):
                    continue
                source_text = candidate_block.get("block_text") or ""
                start_offset = source_text.find(original_text)
                bindings.append(
                    {
                        "must_have_point": point.strip(),
                        "evidence": {
                            "document_id": document.get("document_id") or source.document_id,
                            "document_name": document.get("file_name") or source.document_name,
                            "section_path": candidate_block.get("section_path", "未分类"),
                            "page_no": candidate_block.get("page_no"),
                            "block_id": evidence_block_id,
                            "original_text": original_text,
                            "start_offset": start_offset,
                            "end_offset": start_offset + len(original_text),
                        },
                    }
                )

        # 只要候选证据没有覆盖所有答案要点，就整体回退，避免产生半完整证据链。
        if len(bindings) != len(fallback_points):
            bindings = []
            for point in fallback_points:
                bindings.append(
                    {
                        "must_have_point": point,
                        "evidence": {
                            "document_id": source.document_id,
                            "document_name": source.document_name,
                            "section_path": source.section_path,
                            "page_no": source.page_no,
                            "block_id": source.block_id,
                            "original_text": source.original_text,
                            "start_offset": source.start_offset,
                            "end_offset": source.end_offset,
                        },
                    }
                )
        return bindings

    # ------------------------------------------------------------------
    # 难度初判（FR-DIFF-001 / 002 / 005）
    # ------------------------------------------------------------------
    @staticmethod
    def _rule_difficulty(eiu_type: str, priority: str) -> str:
        """难度写死（#8）：由 EIU 类型/优先级规则映射，确定性、不依赖 LLM。

        规则：
          - P0（监管红线/禁止/例外）→ L2（高价值，必覆盖）
          - 其余类型按语义：threshold/definition/rule/prohibition/exception → L2；
            metric/date/process/change/formula → L1
          - 单段题不做 L3（README §5.1：L3 需跨段多跳），统一 ≤ L2
        """
        if priority == "P0":
            return "L2"
        high = {"threshold", "definition", "rule", "prohibition", "exception"}
        return "L2" if eiu_type in high else "L1"

    @staticmethod
    def _validate_difficulty(difficulty: str, *, single_segment: bool) -> str:
        level = str(difficulty or "L2").strip().upper()
        if level not in {"L1", "L2", "L3"}:
            level = "L2"
        # README §5.1：L3 必须跨段多跳/多项消歧；单段题复查后降级为 L2
        if single_segment and level == "L3":
            level = "L2"
        return level


def _strip_code_fence(text: str) -> str:
    """剥离 ```json ... ``` 等代码块围栏，返回纯 JSON 文本。"""
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL)
    if match:
        return match.group(1).strip()
    return text
