"""固定的智能体中间节点指标。

中间评测是运行级别的可选能力，节点一旦被选中，指标集合固定：

* rewrite：语义相似度，以及有约束标注时的约束 Precision / Recall / F1；
* intent：单标签分类准确率，汇总时计算 Macro-F1；
* rag：RAGAS Context Precision、Context Recall、Faithfulness、Answer Relevancy。

这里不依赖平台内部的 Block / EIU / source_ref。RAGAS 使用评测样本的标准答案、
实际检索文本和智能体回答，适用于外部智能体及外部评测集。
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any

from modules.m05_dataset_lifecycle.services.scoring import score_answer
from modules.shared.core.config import settings

SUPPORTED_NODES = ("rewrite", "intent", "rag")
RAGAS_METRICS = (
    "context_precision",
    "context_recall",
    "faithfulness",
    "answer_relevancy",
)


def normalize_nodes(value: object) -> list[str]:
    """校验并去重运行级节点选择；非法节点由 API 请求直接拒绝。"""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("intermediate_eval.nodes 必须是数组")
    nodes: list[str] = []
    for item in value:
        node = str(item).strip().lower()
        if node not in SUPPORTED_NODES:
            raise ValueError(f"不支持的中间评测节点: {node}")
        if node not in nodes:
            nodes.append(node)
    return nodes


def normalize_intermediate_config(value: dict | None) -> dict:
    """把缺省配置统一为关闭状态，兼容旧运行记录。"""
    config = value if isinstance(value, dict) else {}
    enabled = bool(config.get("enabled"))
    nodes = normalize_nodes(config.get("nodes"))
    return {"enabled": enabled and bool(nodes), "nodes": nodes if enabled else []}


def _contract(sample: dict) -> dict:
    value = sample.get("intermediate_reference") or sample.get("node_contract") or {}
    return value if isinstance(value, dict) else {}


def _outputs(result: dict) -> dict:
    value = result.get("node_outputs") if isinstance(result, dict) else None
    return value if isinstance(value, dict) else {}


def _first(value: object, *keys: str) -> object:
    if isinstance(value, dict):
        for key in keys:
            if value.get(key) is not None:
                return value[key]
    return None


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        nested = _first(value, "text", "content", "answer", "value")
        return _text(nested)
    return str(value).strip()


def _normalize_constraint(value: object) -> str:
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    text = _text(value).lower()
    text = re.sub(r"\s+", "", text)
    return text


def _constraints(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        values = value
    else:
        values = [value]
    result: list[str] = []
    for item in values:
        normalized = _normalize_constraint(item)
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _parse_contexts(value: object) -> list[str]:
    """将外部评测集中的 evidence/reference_contexts 统一为文本列表。"""
    if value is None:
        return []
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return [raw]
        if parsed != raw:
            return _parse_contexts(parsed)
        return [raw]
    if isinstance(value, dict):
        text = _text(value)
        return [text] if text else []
    if isinstance(value, (list, tuple)):
        contexts: list[str] = []
        for item in value:
            contexts.extend(_parse_contexts(item))
        return contexts
    text = _text(value)
    return [text] if text else []


def _retrieved_contexts(result: dict) -> list[str]:
    raw = result.get("retrieved")
    if raw is None:
        rag_output = _outputs(result).get("rag")
        raw = _first(rag_output, "retrieved_contexts", "contexts", "retrieved")
    return _parse_contexts(raw)


def _rewrite_score(sample: dict, result: dict) -> dict:
    contract = _contract(sample).get("rewrite")
    if not isinstance(contract, dict):
        contract = _contract(sample)
    reference = _text(_first(contract, "reference", "reference_text", "rewrite_reference", "text", "gold")) or _text(
        sample.get("rewrite_reference")
    )
    output = _outputs(result).get("rewrite")
    actual = _text(output)
    if not reference or not actual:
        return {"status": "data_missing", "semantic_similarity": None}
    semantic = score_answer(actual, reference, use_semantic=True)
    expected_constraints = _constraints(
        _first(contract, "constraints", "reference_constraints", "rewrite_constraints")
        or sample.get("rewrite_constraints")
    )
    predicted_constraints = _constraints(
        _first(output, "constraints", "preserved_constraints")
    )
    payload: dict[str, Any] = {
        "status": "scored",
        "semantic_similarity": semantic.get("score"),
        "constraint_precision": None,
        "constraint_recall": None,
        "constraint_f1": None,
        "full_constraint_preservation": None,
    }
    if expected_constraints:
        expected = set(expected_constraints)
        predicted = set(predicted_constraints)
        true_positive = len(expected & predicted)
        precision = true_positive / len(predicted) if predicted else 0.0
        recall = true_positive / len(expected)
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        payload.update(
            constraint_precision=round(precision, 4),
            constraint_recall=round(recall, 4),
            constraint_f1=round(f1, 4),
            full_constraint_preservation=bool(expected <= predicted),
        )
    return payload


def _intent_score(sample: dict, result: dict) -> dict:
    contract = _contract(sample).get("intent")
    if not isinstance(contract, dict):
        contract = _contract(sample)
    reference = _text(_first(contract, "label", "intent", "intent_label", "reference")) or _text(
        sample.get("intent_label") or sample.get("intent_id")
    )
    output = _outputs(result).get("intent")
    predicted = _text(_first(output, "label", "intent", "value")) or _text(output)
    if not reference or not predicted:
        return {
            "status": "data_missing",
            "reference": reference or None,
            "predicted": predicted or None,
            "correct": None,
        }
    return {
        "status": "scored",
        "reference": reference,
        "predicted": predicted,
        "correct": reference == predicted,
    }


def _ragas_metric(metric: object, **kwargs: object) -> float:
    result = metric.score(**kwargs)
    value = getattr(result, "value", result)
    return round(float(value), 4)


def _ragas_score(sample: dict, result: dict) -> dict:
    answer = _text(result.get("answer"))
    question = _text(sample.get("question"))
    reference = _text(sample.get("gold_answer"))
    contexts = _retrieved_contexts(result)
    if not question or not answer or not reference or not contexts:
        return {"status": "data_missing", "metrics": {name: None for name in RAGAS_METRICS}}
    try:
        from openai import AsyncOpenAI
        from ragas.embeddings import embedding_factory
        from ragas.llms import llm_factory
        from ragas.metrics.collections import (
            AnswerRelevancy,
            ContextPrecision,
            ContextRecall,
            Faithfulness,
        )
    except ImportError as exc:
        return {
            "status": "unavailable",
            "error": "RAGAS 评测依赖未安装",
            "metrics": {name: None for name in RAGAS_METRICS},
            "detail": str(exc),
        }
    if not settings.llm_api_key or settings.llm_api_key.startswith("sk-xxx"):
        return {
            "status": "unavailable",
            "error": "RAGAS 评测模型未配置",
            "metrics": {name: None for name in RAGAS_METRICS},
        }
    try:
        client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_api_base)
        llm = llm_factory(settings.llm_model, client=client)
        embeddings = embedding_factory(
            "openai", model="text-embedding-3-small", client=client
        )
        kwargs = {
            "user_input": question,
            "reference": reference,
            "response": answer,
            "retrieved_contexts": contexts,
        }
        metrics = {
            "context_precision": _ragas_metric(ContextPrecision(llm=llm), **kwargs),
            "context_recall": _ragas_metric(ContextRecall(llm=llm), **kwargs),
            "faithfulness": _ragas_metric(Faithfulness(llm=llm), **kwargs),
            "answer_relevancy": _ragas_metric(
                AnswerRelevancy(llm=llm, embeddings=embeddings), **kwargs
            ),
        }
        return {"status": "scored", "metrics": metrics}
    except Exception as exc:  # noqa: BLE001 — 单题 RAGAS 错误须保留在结果中
        return {
            "status": "error",
            "error": "RAGAS 评测失败",
            "metrics": {name: None for name in RAGAS_METRICS},
            "detail": str(exc)[:500],
        }


def score_intermediate(sample: dict, result: dict, nodes: list[str]) -> dict:
    """单题中间评分；最终答案分数仍由原 score_case 独立计算。"""
    scores: dict[str, dict] = {}
    if "rewrite" in nodes:
        scores["rewrite"] = _rewrite_score(sample, result)
    if "intent" in nodes:
        scores["intent"] = _intent_score(sample, result)
    if "rag" in nodes:
        scores["rag"] = _ragas_score(sample, result)
    return {"enabled": bool(scores), "nodes": scores}


def _f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def _classification_aggregate(items: list[dict]) -> dict:
    scored = [item for item in items if item.get("status") == "scored"]
    if not scored:
        return {"status": "data_missing", "accuracy": None, "macro_f1": None, "by_label": {}, "confusion": {}}
    labels = sorted({item["reference"] for item in scored} | {item["predicted"] for item in scored})
    by_label: dict[str, dict] = {}
    confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for item in scored:
        confusion[item["reference"]][item["predicted"]] += 1
    f1_values: list[float] = []
    for label in labels:
        tp = sum(1 for item in scored if item["reference"] == label and item["predicted"] == label)
        fp = sum(1 for item in scored if item["reference"] != label and item["predicted"] == label)
        fn = sum(1 for item in scored if item["reference"] == label and item["predicted"] != label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = _f1(precision, recall)
        f1_values.append(f1)
        by_label[label] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": tp + fn,
        }
    return {
        "status": "scored",
        "accuracy": round(sum(item["correct"] for item in scored) / len(scored), 4),
        "macro_f1": round(sum(f1_values) / len(f1_values), 4),
        "by_label": by_label,
        "confusion": {key: dict(value) for key, value in confusion.items()},
        "scored": len(scored),
    }


def aggregate_intermediate(results: list[dict], nodes: list[str]) -> dict:
    """汇总已持久化的中间分数，缺失节点不计入 0 分。"""
    output: dict[str, dict] = {}
    for node in nodes:
        items = [
            (result.get("scores") or {}).get("intermediate", {}).get("nodes", {}).get(node)
            for result in results
        ]
        items = [item for item in items if isinstance(item, dict)]
        if node == "intent":
            output[node] = _classification_aggregate(items)
            continue
        scored = [item for item in items if item.get("status") == "scored"]
        if node == "rewrite":
            fields = ["semantic_similarity", "constraint_precision", "constraint_recall", "constraint_f1"]
        else:
            fields = list(RAGAS_METRICS)
            items = [item.get("metrics", {}) for item in scored]
        summary: dict[str, Any] = {field: None for field in fields}
        for field in fields:
            values = [float(item[field]) for item in items if item.get(field) is not None]
            if values:
                summary[field] = round(sum(values) / len(values), 4)
        summary["status"] = "scored" if scored else "data_missing"
        summary["scored"] = len(scored)
        if node == "rewrite":
            complete = [
                item.get("full_constraint_preservation")
                for item in scored
                if item.get("full_constraint_preservation") is not None
            ]
            summary["full_constraint_preservation_rate"] = (
                round(sum(bool(value) for value in complete) / len(complete), 4)
                if complete
                else None
            )
        output[node] = summary
    return {"enabled": bool(output), "nodes": output}
