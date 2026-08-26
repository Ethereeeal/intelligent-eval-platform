"""Deterministic document-level Claim relationship and completeness diagnostics."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from itertools import combinations
from typing import Any


_SPACE_RE = re.compile(r"[\s，。；：、】【（）()、,.;:]+")
_ARTICLE_RE = re.compile(r"第\s*([一二三四五六七八九十百千万零〇两0-9]+)\s*条")
_NEGATIVE_MODALITIES = {"不得", "禁止", "不准", "不允许", "不接受", "不可"}
_POSITIVE_MODALITIES = {"应当", "必须", "可以", "仅接受", "可接受"}


def _normalise(value: str) -> str:
    return _SPACE_RE.sub("", value or "").lower()


def _shingles(value: str) -> set[str]:
    compact = _normalise(value)
    if len(compact) < 3:
        return {compact} if compact else set()
    return {compact[index:index + 3] for index in range(len(compact) - 2)}


def _overlap(left: str, right: str) -> float:
    left_terms, right_terms = _shingles(left), _shingles(right)
    if not left_terms or not right_terms:
        return 0.0
    return len(left_terms & right_terms) / len(left_terms | right_terms)


def _relation(left: dict[str, Any], right: dict[str, Any]) -> str | None:
    left_statement = str(left.get("statement") or "")
    right_statement = str(right.get("statement") or "")
    left_normalised, right_normalised = _normalise(left_statement), _normalise(right_statement)
    if not left_normalised or not right_normalised:
        return None
    if left_normalised == right_normalised:
        return "exact_duplicate"

    left_subject = _normalise(str(left.get("subject") or ""))
    right_subject = _normalise(str(right.get("subject") or ""))
    left_predicate = _normalise(str(left.get("predicate") or ""))
    right_predicate = _normalise(str(right.get("predicate") or ""))
    left_object = _normalise(str(left.get("object") or ""))
    right_object = _normalise(str(right.get("object") or ""))
    left_modality = str(left.get("modality") or "")
    right_modality = str(right.get("modality") or "")
    same_subject_predicate = bool(left_subject and left_subject == right_subject and left_predicate == right_predicate)
    opposite_modality = (
        (left_modality in _NEGATIVE_MODALITIES and right_modality in _POSITIVE_MODALITIES)
        or (right_modality in _NEGATIVE_MODALITIES and left_modality in _POSITIVE_MODALITIES)
    )
    same_object = bool(left_object and left_object == right_object)
    if same_subject_predicate and opposite_modality and (same_object or _overlap(left_statement, right_statement) >= 0.45):
        return "conflict"
    if left_normalised in right_normalised or right_normalised in left_normalised:
        return "contains"
    if _overlap(left_statement, right_statement) >= 0.62:
        return "overlaps"
    return None


def analyse_claim_relationships(eius: list[dict[str, Any]], *, sample_limit: int = 100) -> dict[str, Any]:
    """Classify likely duplicate/containment/overlap/conflict pairs within one document.

    This is a diagnostic, not an automatic merge. The caller must keep all rows and
    let an LLM reviewer or a user decide whether the evidence should be consolidated.
    """
    by_document: dict[int | None, list[dict[str, Any]]] = defaultdict(list)
    for eiu in eius:
        statement = str(eiu.get("statement") or "")
        if statement and not statement.startswith("["):
            by_document[eiu.get("document_id")].append(eiu)

    counts: Counter[str] = Counter()
    samples: list[dict[str, Any]] = []
    for document_id, claims in by_document.items():
        for left, right in combinations(claims, 2):
            relation_type = _relation(left, right)
            if not relation_type:
                continue
            counts[relation_type] += 1
            if len(samples) < sample_limit:
                samples.append({
                    "document_id": document_id,
                    "relation_type": relation_type,
                    "left_eiu_id": left.get("eiu_id"),
                    "right_eiu_id": right.get("eiu_id"),
                    "left_statement": left.get("statement"),
                    "right_statement": right.get("statement"),
                })
    return {
        "exact_duplicate": counts["exact_duplicate"],
        "contains": counts["contains"],
        "overlaps": counts["overlaps"],
        "conflicts": counts["conflict"],
        "total": sum(counts.values()),
        "samples": samples,
    }


def audit_document_claim_coverage(
    blocks: list[dict[str, Any]],
    eius: list[dict[str, Any]],
    *,
    sample_limit: int = 20,
) -> list[dict[str, Any]]:
    """Report missing/weak Claim coverage per document without changing coverage gates."""
    claims_by_document: dict[int | None, list[dict[str, Any]]] = defaultdict(list)
    for eiu in eius:
        claims_by_document[eiu.get("document_id")].append(eiu)
    blocks_by_document: dict[int | None, list[dict[str, Any]]] = defaultdict(list)
    for block in blocks:
        blocks_by_document[block.get("document_id")].append(block)

    audits: list[dict[str, Any]] = []
    for document_id, document_blocks in blocks_by_document.items():
        substantive = [block for block in document_blocks if block.get("block_type") != "title"]
        claims = claims_by_document.get(document_id, [])
        claim_block_ids = {int(claim["block_id"]) for claim in claims if claim.get("block_id") is not None}
        viable_block_ids = {
            int(claim["block_id"])
            for claim in claims
            if claim.get("is_questionable") and claim.get("block_id") is not None
        }
        without_claim = [block for block in substantive if int(block["block_id"]) not in claim_block_ids]
        excluded_only = [
            block for block in substantive
            if int(block["block_id"]) in claim_block_ids and int(block["block_id"]) not in viable_block_ids
        ]
        long_single_claim = [
            block for block in substantive
            if len(str(block.get("block_text") or "")) >= 320
            and sum(1 for claim in claims if claim.get("block_id") == block.get("block_id")) == 1
        ]
        known_articles = {
            str((block.get("metadata_json") or {}).get("article_no") or "")
            for block in document_blocks
            if block.get("block_type") == "title"
        }
        known_articles.update(
            f"第{article}条"
            for block in document_blocks
            for article in _ARTICLE_RE.findall(str(block.get("block_text") or "")[:40])
        )
        unresolved_references = [
            block for block in substantive
            if any(f"第{article}条" not in known_articles for article in _ARTICLE_RE.findall(str(block.get("block_text") or "")))
        ]
        audits.append({
            "document_id": document_id,
            "substantive_block_count": len(substantive),
            "blocks_without_claim_count": len(without_claim),
            "excluded_only_block_count": len(excluded_only),
            "long_single_claim_block_count": len(long_single_claim),
            "unresolved_reference_block_count": len(unresolved_references),
            "samples": {
                "blocks_without_claim": [block["block_id"] for block in without_claim[:sample_limit]],
                "excluded_only_blocks": [block["block_id"] for block in excluded_only[:sample_limit]],
                "long_single_claim_blocks": [block["block_id"] for block in long_single_claim[:sample_limit]],
                "unresolved_reference_blocks": [block["block_id"] for block in unresolved_references[:sample_limit]],
            },
        })
    return audits
