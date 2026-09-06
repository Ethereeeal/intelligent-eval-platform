"""EIU 自动质量门禁与文档内重要性判定。

本模块把抽取阶段产生的候选统一收口为三种对外状态：
green（可出题）、yellow（仅高重要性且自动补齐后仍需处理）、red（归档排除）。
P0/P1/P2 是内部的“相对文档目的的重要性”，绝不能由规则类型直接写死。
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from typing import Any


QUALITY_POLICY_VERSION = "eiu-gate-v1"
IMPORTANCE_LEVELS = {"P0", "P1", "P2"}
EVALUATION_PROFILES = {"developer_smoke", "test_full", "business"}

_SPACE_RE = re.compile(r"[\s，。；：、“”‘’（）()《》]+")
_EXAMPLE_RE = re.compile(r"例如|示例|举例|备注|说明")
_RISK_SIGNAL_RE = re.compile(r"不得|禁止|仅|除外|例外|风险|责任|处罚|审批|授权|条件|范围")


def _normalize(value: str) -> str:
    return _SPACE_RE.sub("", value or "").lower()


def _canonical_key(item: dict[str, Any]) -> str:
    """只对同一规范声明建立稳定意图键，避免把相近但独立的规则硬合并。"""
    parts = [
        _normalize(str(item.get("subject") or "")),
        _normalize(str(item.get("predicate") or "")),
        _normalize(str(item.get("object") or "")),
        _normalize(str(item.get("modality") or "")),
        _normalize(json.dumps(item.get("qualifiers") or item.get("constraints") or {}, ensure_ascii=False, sort_keys=True)),
        _normalize(str(item.get("section_path") or "")),
        _normalize(str(item.get("statement") or "")),
    ]
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"intent-{digest}"


def _quality_reasons(item: dict[str, Any]) -> list[str]:
    checks = item.get("quality_checks") or {}
    reasons: list[str] = []
    for name in ("fidelity", "completeness", "atomicity"):
        check = checks.get(name) or {}
        if check.get("status") != "pass":
            reasons.extend(str(reason) for reason in (check.get("reasons") or []) if reason)
    return list(dict.fromkeys(reasons))


class EiuGatePolicy:
    """对同一文档的候选做批量重要性、去重与处置判定。"""

    def __init__(self, llm: Any | None = None) -> None:
        self.llm = llm

    def apply_document(
        self,
        *,
        document: dict[str, Any],
        items: list[dict[str, Any]],
        blocks: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """返回已更新 EIU 与可持久化的文档质量反馈。

        LLM 可用时按整篇文档（标题、段落路径、所有候选）判定 P0/P1/P2；离线时
        只给保守的 P1/P2 兜底，避免把规则谓词错误等同于“核心内容”。
        """
        result = [dict(item) for item in items]
        for index, item in enumerate(result):
            item["canonical_intent_key"] = _canonical_key(item)
            item["importance_signals"] = self._importance_signals(item)
            item["quality_policy_version"] = QUALITY_POLICY_VERSION
            item["_policy_index"] = index

        importance = self._classify_importance(document, result, blocks)
        for item in result:
            decision = importance.get(item["_policy_index"], {})
            item["content_priority"] = decision.get("importance_level", "P1")
            item["importance_reason"] = decision.get("reason") or "按文档整体上下文完成重要性判定"
            item["evaluation_profiles"] = decision.get("evaluation_profiles") or self._default_profiles(item)
            self._apply_quality_disposition(item)

        duplicate_findings = self._archive_true_duplicates(result)
        findings = self._build_quality_findings(document, result, duplicate_findings)
        for item in result:
            item.pop("_policy_index", None)
        return result, findings

    def _importance_signals(self, item: dict[str, Any]) -> list[str]:
        statement = str(item.get("statement") or "")
        signals: list[str] = []
        if _RISK_SIGNAL_RE.search(statement):
            signals.append("包含规则边界、例外或风险相关表述")
        if item.get("eiu_type") in {"process", "threshold", "exception"}:
            signals.append("候选可能涉及执行条件或例外")
        if _EXAMPLE_RE.search(statement):
            signals.append("候选含示例/说明语气")
        return signals

    def _classify_importance(
        self,
        document: dict[str, Any],
        items: list[dict[str, Any]],
        blocks: list[dict[str, Any]],
    ) -> dict[int, dict[str, Any]]:
        decisions = self._ask_llm_for_importance(document, items, blocks)
        if decisions:
            return decisions

        # 离线降级：不把“不得/必须”等规则类型直接升级为 P0。只有明显背景/示例
        # 降为 P2，其余保守地标为 P1，并等待具备模型时按文档整体重算。
        fallback: dict[int, dict[str, Any]] = {}
        for item in items:
            statement = str(item.get("statement") or "")
            priority = "P2" if _EXAMPLE_RE.search(statement) else "P1"
            fallback[item["_policy_index"]] = {
                "importance_level": priority,
                "reason": "LLM 不可用，采用不将规则类型等同于文档重要性的保守降级判定",
                "evaluation_profiles": self._default_profiles(item, priority=priority),
            }
        return fallback

    def _ask_llm_for_importance(
        self,
        document: dict[str, Any],
        items: list[dict[str, Any]],
        blocks: list[dict[str, Any]],
    ) -> dict[int, dict[str, Any]]:
        if self.llm is None or getattr(self.llm, "use_offline", True):
            return {}
        payload = {
            "document": {
                "name": document.get("file_name"),
                "purpose": document.get("purpose"),
                "sections": list(dict.fromkeys(
                    str(block.get("section_path") or "") for block in blocks if block.get("section_path")
                ))[:80],
            },
            "candidates": [
                {
                    "candidate_id": item["_policy_index"],
                    "statement": item.get("statement"),
                    "section_path": item.get("section_path"),
                    "eiu_type": item.get("eiu_type"),
                    "signals": item.get("importance_signals"),
                }
                for item in items
            ],
        }
        system_prompt = (
            "你是评测集知识覆盖规划器。仅依据同一文档的目的、章节结构和全部候选，"
            "判定每条候选相对该文档的重要性。P0=缺失会误解核心规则/边界/风险/关键流程；"
            "P1=有助理解但缺失不改变核心结论；P2=背景、示例、重复或低价值延伸。"
            "不得根据‘不得/必须’等单个规则类型直接判 P0。返回 JSON 数组，每项含"
            "candidate_id、importance_level(P0/P1/P2)、reason、evaluation_profiles"
            "（developer_smoke/test_full/business 的子集）。"
        )
        try:
            raw = self.llm.extract_json(system_prompt, json.dumps(payload, ensure_ascii=False))
        except Exception:  # LLM 故障必须降级，不能中断文档处理
            return {}
        decisions: dict[int, dict[str, Any]] = {}
        valid_indices = {item["_policy_index"] for item in items}
        for row in raw:
            try:
                index = int(row.get("candidate_id"))
            except (TypeError, ValueError):
                continue
            level = str(row.get("importance_level") or "").upper()
            if index not in valid_indices or level not in IMPORTANCE_LEVELS:
                continue
            profiles = [
                profile for profile in (row.get("evaluation_profiles") or [])
                if profile in EVALUATION_PROFILES
            ]
            decisions[index] = {
                "importance_level": level,
                "reason": str(row.get("reason") or "LLM 基于全文上下文判定"),
                "evaluation_profiles": profiles,
            }
        return decisions if len(decisions) == len(items) else {}

    def _default_profiles(self, item: dict[str, Any], *, priority: str | None = None) -> list[str]:
        level = priority or str(item.get("content_priority") or "P1")
        if level == "P0":
            return ["developer_smoke", "test_full", "business"]
        if level == "P1":
            return ["test_full", "business"]
        return ["test_full"]

    def _apply_quality_disposition(self, item: dict[str, Any]) -> None:
        quality_ok = item.get("quality_status") == "verified"
        priority = str(item.get("content_priority") or "P1")
        reasons = _quality_reasons(item)
        if quality_ok:
            item.update(
                is_questionable=True,
                auto_disposition="green",
                route_color="green",
                review_action="ready_for_generation",
                exclusion_reason=None,
            )
            return
        if priority == "P0":
            item.update(
                is_questionable=True,
                quality_status="needs_review",
                auto_disposition="yellow",
                route_color="yellow",
                review_action="manual_review",
                exclusion_reason=None,
            )
            item["route_reasons"] = list(dict.fromkeys((item.get("route_reasons") or []) + reasons))
            return
        exclusion_reason = "；".join(reasons) or "未满足 EIU 自动质量门禁"
        item.update(
            is_questionable=False,
            quality_status="rejected",
            auto_disposition="red",
            route_color="red",
            review_action="archive",
            exclusion_reason=exclusion_reason[:120],
        )
        item["route_reasons"] = list(dict.fromkeys((item.get("route_reasons") or []) + reasons))

    def _archive_true_duplicates(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """仅归并声明、结构化条件和章节范围均相同的候选；相似规则不能据此丢失。"""
        by_statement: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in items:
            by_statement[str(item.get("canonical_intent_key") or "")].append(item)
        findings: list[dict[str, Any]] = []
        for key, group in by_statement.items():
            if not key or len(group) < 2:
                continue
            winner = min(
                group,
                key=lambda item: (
                    item.get("auto_disposition") != "green",
                    item.get("quality_score") is None,
                    -(item.get("quality_score") or 0),
                    item.get("_policy_index", 0),
                ),
            )
            for duplicate in group:
                duplicate["canonical_intent_key"] = winner["canonical_intent_key"]
                if duplicate is winner:
                    continue
                duplicate.update(
                    is_questionable=False,
                    quality_status="rejected",
                    auto_disposition="red",
                    route_color="red",
                    review_action="archive_duplicate",
                    exclusion_reason="与同文档规范声明完全重复，已归并到同一知识意图",
                )
            findings.append({
                "code": "duplicate_canonicalized",
                "severity": "hint",
                "message": f"发现 {len(group)} 条完全重复的知识候选，已保留一个规范意图并归档其余副本",
                "block_ids": [item.get("block_id") for item in group if item.get("block_id")],
                "eiu_ids": [item.get("eiu_id") for item in group if item.get("eiu_id")],
                "system_action": "已自动归并完全重复候选；不同条件、例外或结论的规则不会合并",
            })
        return findings

    def _build_quality_findings(
        self,
        document: dict[str, Any],
        items: list[dict[str, Any]],
        duplicates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        findings = list(duplicates)
        for item in items:
            reasons = _quality_reasons(item)
            if item.get("auto_disposition") == "yellow":
                findings.append({
                    "code": "p0_unresolved",
                    "severity": "risk",
                    "message": "核心内容经自动补齐与质量检查后仍不完整，建议补充原文定义、引用条款或拆分复合规则",
                    "block_ids": [item.get("block_id")],
                    "eiu_ids": [item.get("eiu_id")] if item.get("eiu_id") else [],
                    "system_action": "已保留在待复核，未进入自动出题",
                    "details": reasons,
                })
            elif item.get("auto_disposition") == "red" and reasons:
                findings.append({
                    "code": "knowledge_archived",
                    "severity": "hint",
                    "message": "存在未满足质量门禁的非核心候选，系统已归档排除出题",
                    "block_ids": [item.get("block_id")],
                    "eiu_ids": [item.get("eiu_id")] if item.get("eiu_id") else [],
                    "system_action": "已归档，不影响绿色知识点出题",
                    "details": reasons,
                })
        return findings
