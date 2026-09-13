"""EIU 条款级审查编排。

该模块只负责黄色/红色路径的审查流程：同条款批审、上下文图谱扩展、
二次审查一致性和证据绑定。规则候选、数据库写入和任务编排仍由
``eiu_extractor.EiuExtractorService`` 负责。

采用 mixin 是为了保持现有 ``EiuExtractorService`` 公共接口和调用方不变，
同时让审查流程可以独立测试和后续替换为异步批处理实现。
"""
from __future__ import annotations

from typing import Any

from modules.m02_eiu_coverage.services.context_bundle import ContextBundleBuilder
from modules.m02_eiu_coverage.services.llm_client import LLMError


class EiuReviewMixin:
    """为抽取服务提供条款级 LLM 审查能力。"""

    @staticmethod
    def _review_utils():
        # 延迟导入，避免 eiu_extractor 导入本 mixin 时形成循环依赖。
        from modules.m02_eiu_coverage.services import eiu_extractor

        return eiu_extractor

    @staticmethod
    def _build_neighbors(document_blocks: list[list[dict]]) -> dict[int, dict[str, str]]:
        neighbors: dict[int, dict] = {}
        for blocks in document_blocks:
            neighbors.update(ContextBundleBuilder(blocks).build_all())
        return neighbors

    @staticmethod
    def _review_cache_key(document: dict, block_id: int) -> tuple[str, int]:
        document_key = str(document.get("document_id") or document.get("file_name") or "unknown")
        return document_key, int(block_id)

    def _take_article_review_cache(self, document: dict, block_id: int) -> list[dict] | None:
        return self._article_review_cache.pop(self._review_cache_key(document, block_id), None)

    def _partition_article_review_items(
        self,
        document: dict,
        current_block_id: int,
        context: dict,
        raw_items: list[dict],
    ) -> list[dict]:
        article_ids = {
            int(entry["block_id"])
            for entry in context.get("article_batch") or []
            if isinstance(entry, dict) and entry.get("block_id") is not None
        }
        if len(article_ids) < 2:
            return raw_items

        current_items: list[dict] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            try:
                item_block_id = int(item.get("block_id"))
            except (TypeError, ValueError):
                current_items.append(item)
                continue
            if item_block_id == current_block_id:
                current_items.append(item)
            elif item_block_id in article_ids:
                cache_key = self._review_cache_key(document, item_block_id)
                self._article_review_cache.setdefault(cache_key, []).append(item)
            else:
                # 模型误标 Block 时不能静默丢弃当前条款的结果。
                current_items.append(item)
        return current_items

    @staticmethod
    def _review_signature(raw_items: list[dict]) -> frozenset[tuple[str, str, str]]:
        utils = EiuReviewMixin._review_utils()
        signature: set[tuple[str, str, str]] = set()
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            statement = utils._clean_statement(str(item.get("statement") or ""))
            if not statement:
                continue
            signature.add((
                str(item.get("block_id") or "current"),
                utils._review_action(item.get("review_action")),
                statement,
            ))
        return frozenset(signature)

    def _extract_block(self, block: dict, document: dict, context: dict[str, str]) -> list[dict]:
        """执行单个 Block 的规则候选、LLM 审查和证据归档。"""
        utils = self._review_utils()
        meta = block.get("metadata_json") or {}
        if block.get("block_type") == "excel_row" and (meta.get("question") or "").strip():
            text = str(meta.get("question")).strip()
        else:
            text = block["block_text"]
        if utils.is_skippable(text):
            return []

        rule_items = utils.deterministic_extract(text)
        for candidate_index, item in enumerate(rule_items, start=1):
            item["block_id"] = block["block_id"]
            item["candidate_id"] = block["block_id"] * 1000 + candidate_index
            item["extraction_model"] = "hybrid-rule"
            item["extraction_confidence"] = 0.9

        yellow_reasons = utils._yellow_route_reasons(block, rule_items)
        if rule_items and not yellow_reasons:
            for item in rule_items:
                item["route_color"] = "green"
                item["route_reasons"] = ["单一直接候选，进入确定性验证"]
                item["review_action"] = "pass"
            return rule_items

        if rule_items and self.llm.use_offline:
            for item in rule_items:
                item["force_needs_review"] = True
                item["extraction_model"] = "hybrid-rule-yellow-pending"
                item["route_color"] = "red"
                item["route_reasons"] = yellow_reasons + ["LLM 当前不可用，转人工复核"]
                item["review_action"] = "human_review"
            return rule_items

        if self.llm.use_offline:
            return []

        try:
            review_attempts = 1
            review_inconsistent = False
            raw_items = self._take_article_review_cache(document, block["block_id"])
            if raw_items is None:
                raw_items = self._partition_article_review_items(
                    document,
                    block["block_id"],
                    context,
                    self.llm.extract_json(
                        self.system_prompt,
                        self._build_user_prompt(block, document, context, rule_candidates=rule_items),
                    ),
                )
            initial_signature = self._review_signature(raw_items)
            requests = utils._context_requests(raw_items)
            resolver = context.get("_resolver")
            if requests and resolver is not None:
                expanded_context = resolver.expand(context, requests)
                if expanded_context.get("resolved_requests"):
                    review_attempts = 2
                    raw_items = self._partition_article_review_items(
                        document,
                        block["block_id"],
                        expanded_context,
                        self.llm.extract_json(
                            self.system_prompt,
                            self._build_user_prompt(
                                block, document, expanded_context, rule_candidates=rule_items
                            ),
                        ),
                    )
                    retried_signature = self._review_signature(raw_items)
                    review_inconsistent = bool(
                        initial_signature
                        and retried_signature
                        and initial_signature != retried_signature
                    )
                    context = expanded_context
                elif rule_items:
                    for candidate in rule_items:
                        candidate["force_needs_review"] = True
                        candidate["route_color"] = "red"
                        candidate["review_action"] = "human_review"
                        candidate["route_reasons"] = yellow_reasons + [
                            "文档上下文映射未找到 LLM 请求的补充证据"
                        ]
                    return rule_items
        except LLMError:
            if rule_items:
                for item in rule_items:
                    item["force_needs_review"] = True
                    item["extraction_model"] = "hybrid-rule-yellow-pending"
                    item["route_color"] = "red"
                    item["route_reasons"] = yellow_reasons + ["LLM 审查调用失败，转人工复核"]
                    item["review_action"] = "human_review"
                return rule_items
            return []

        items: list[dict] = []
        seen: set[str] = set()
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            action = utils._review_action(item.get("review_action"))
            statement = utils._clean_statement(str(item.get("statement", "")))
            if not statement or statement in seen:
                continue
            seen.add(statement)
            classification = utils._classify(statement)
            if classification is None:
                continue
            eiu_type, priority = classification
            evidence_blocks, evidence_details = utils._review_evidence(
                context, item.get("evidence_block_ids"), block["block_id"]
            )
            source_indexes = item.get("source_candidate_indexes")
            source_candidate_ids = [
                rule_items[index - 1]["candidate_id"]
                for index in source_indexes
                if isinstance(index, int) and 0 < index <= len(rule_items)
            ] if isinstance(source_indexes, list) else []
            is_questionable = bool(item.get("is_questionable", True)) and action != "reject"
            normalized = {
                "statement": utils._truncate_statement(statement),
                "eiu_type": eiu_type,
                "content_priority": priority,
                "constraints": utils._constraints_for(statement),
                "evidence_blocks": evidence_blocks,
                "evidence_details": evidence_details,
                "source_candidate_ids": source_candidate_ids,
                "is_questionable": is_questionable,
                "exclusion_reason": (
                    None if is_questionable
                    else str(item.get("exclusion_reason") or "语义不可出题")[:128]
                ),
                "extraction_model": "hybrid-llm",
                "extraction_confidence": 0.7,
                "route_color": "yellow",
                "route_reasons": yellow_reasons or ["规则无法稳定分类，进入 LLM 审查"],
                "review_action": "human_review" if review_inconsistent else action,
                "review_attempts": review_attempts,
                "review_model": self.llm.model,
                "review_prompt_version": "eiu-yellow-v1",
            }
            normalized.update(utils._claim_fields(statement, normalized["constraints"]))
            if review_inconsistent:
                normalized["route_reasons"] = [
                    *(normalized.get("route_reasons") or []),
                    "LLM 两次审查结论不一致，转人工复核",
                ]
            if action == "human_review" or review_inconsistent:
                normalized["force_needs_review"] = True
                normalized["route_color"] = "red"
            items.append(normalized)
        return items

    @staticmethod
    def _build_user_prompt(
        block: dict,
        document: dict,
        context: dict[str, str],
        *,
        rule_candidates: list[dict] | None = None,
    ) -> str:
        utils = EiuReviewMixin._review_utils()
        candidate_text = "（规则未抽到候选，请直接抽取）"
        if rule_candidates:
            candidate_text = "\n".join(
                f"- {item.get('statement', '')}（{item.get('eiu_type', '')}/{item.get('content_priority', '')}）"
                for item in rule_candidates
            )
        article_batch_text = "（当前条款没有可批审的其他 Block）"
        article_batch = context.get("article_batch") or []
        if len(article_batch) > 1:
            batch_entries: list[str] = []
            for entry in article_batch:
                if not isinstance(entry, dict):
                    continue
                batch_block_id = entry.get("block_id")
                batch_source = str(entry.get("text") or "")
                batch_candidates = utils.deterministic_extract(batch_source)
                batch_candidate_text = "；".join(
                    candidate.get("statement", "") for candidate in batch_candidates
                ) or "（规则未抽到候选）"
                batch_entries.append(
                    f"- block_id={batch_block_id}: {batch_source}\n  规则候选: {batch_candidate_text}"
                )
            article_batch_text = "\n".join(batch_entries) or article_batch_text
        batch_contract = (
            "Each item must include block_id, selecting one block_id from the clause batch below.\n"
            if len(article_batch) > 1 else ""
        )
        return (
            "## 文档信息\n"
            f"- 文档名: {document['file_name']}\n"
            f"- 章节路径: {block['section_path']}\n\n"
            "## 上文（前一个 Block）\n"
            f"{context['prev'] or '（无）'}\n\n"
            "## 当前段落\n"
            f"{block['block_text']}\n\n"
            "## Clause context (structured evidence)\n"
            f"Parent clause: {context.get('parent') or 'none'}\n"
            f"List lead: {context.get('lead') or 'none'}\n"
            f"Same article: {context.get('same_article') or 'none'}\n"
            f"Referenced articles: {context.get('references') or 'none'}\n"
            f"Definitions: {context.get('definitions') or 'none'}\n"
            f"Table headers: {context.get('table_headers') or 'none'}\n"
            f"Allowed evidence blocks and roles: {context.get('evidence_catalog') or 'current'}\n"
            f"Context-map expanded evidence: {context.get('expanded_context') or 'none'}\n"
            f"Unresolved requests: {context.get('unresolved_requests') or 'none'}\n\n"
            "## 下文（后一个 Block）\n"
            f"{context['next'] or '（无）'}\n\n"
            "## 规则候选（黄色审查输入）\n"
            f"{candidate_text}\n\n"
            "## 同条款批审输入（按 block_id 返回）\n"
            f"{article_batch_text}\n\n"
            "## Review output contract\n"
            "Return a JSON array. Each item must include review_action: pass, split, merge, complete_context, reject, or human_review.\n"
            f"{batch_contract}"
            "For split/merge, include source_candidate_indexes (1-based indexes from the rule candidates).\n"
            "For evidence, include evidence_block_ids selected only from the Context Bundle source blocks.\n"
            "If required evidence is absent, include context_requests with kind (definition/reference/condition/subject), query, and optional article_no; do not invent evidence.\n"
            "Use human_review when evidence remains incomplete, a reference cannot be resolved, or the decision is uncertain.\n\n"
            "请审查当前段落及上述候选：对同一事实的重复强调、包含关系或正反表述合并为一条完整 EIU；"
            "需要独立判断真伪的规则才拆分；补全当前段落已明确支持的主体、条件和范围；"
            "不得补写原文未出现的事实。若证据无法支持完整、可回答的陈述，则标记 is_questionable=false。"
        )
