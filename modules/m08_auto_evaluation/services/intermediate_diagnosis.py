"""中间节点诊断与优化建议。

先用稳定的阈值规则定位异常，再在确有指标异常且模型可用时请求 LLM
生成解释和改进建议。诊断不改变原始分数、运行通过状态或评测集内容。
"""
from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

from modules.shared.core.config import settings
from modules.shared.core.llm_client import LLMError, call

DEFAULT_THRESHOLDS = {
    "rewrite.semantic_similarity": 0.70,
    "rewrite.constraint_precision": 0.80,
    "rewrite.constraint_recall": 0.80,
    "rewrite.constraint_f1": 0.80,
    "rag.context_precision": 0.70,
    "rag.context_recall": 0.70,
    "rag.faithfulness": 0.70,
    "rag.answer_relevancy": 0.70,
}

_NODE_LABELS = {"rewrite": "改写", "intent": "意图识别", "rag": "RAG"}
_METRIC_LABELS = {
    "semantic_similarity": "语义相似度",
    "constraint_precision": "约束 Precision",
    "constraint_recall": "约束 Recall",
    "constraint_f1": "约束 F1",
    "context_precision": "Context Precision",
    "context_recall": "Context Recall",
    "faithfulness": "Faithfulness",
    "answer_relevancy": "Answer Relevancy",
}
_DATA_STATUSES = {"data_missing", "unavailable", "error"}


def _bounded_text(value: object, limit: int = 800) -> str:
    text = str(value or "").strip()
    return text[:limit]


def _severity(value: float, threshold: float) -> str:
    return "high" if value < threshold * 0.7 else "medium"


def _issue(
    *,
    node: str,
    code: str,
    message: str,
    suggestion: str,
    severity: str = "medium",
    metric: str | None = None,
    value: float | None = None,
    threshold: float | None = None,
) -> dict:
    return {
        "node": node,
        "code": code,
        "severity": severity,
        "metric": metric,
        "value": round(value, 4) if value is not None else None,
        "threshold": threshold,
        "message": message,
        "suggestion": suggestion,
    }


def _missing_issue(node: str, status: str, detail: object = None) -> dict:
    label = _NODE_LABELS.get(node, node)
    if status == "data_missing":
        message = f"{label}没有返回完成该节点评测所需的标准数据或实际输出"
        suggestion = "检查评测集参考字段和适配器的节点输出映射"
    elif status == "unavailable":
        message = f"{label}评测不可用：所需评测依赖或模型未配置"
        suggestion = "补齐节点评测依赖和模型配置后重新运行"
    else:
        message = f"{label}评测执行异常"
        suggestion = "查看该节点评测错误详情，修复数据或调用配置后复测"
    if detail:
        message += f"（{_bounded_text(detail, 240)}）"
    return _issue(
        node=node,
        code=f"{node}.{status}",
        message=message,
        suggestion=suggestion,
        severity="low",
    )


def _metric_issue(node: str, metric: str, value: object) -> dict | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    threshold = DEFAULT_THRESHOLDS.get(f"{node}.{metric}")
    if threshold is None or numeric >= threshold:
        return None
    label = _NODE_LABELS.get(node, node)
    metric_label = _METRIC_LABELS.get(metric, metric)
    return _issue(
        node=node,
        code=f"{node}.{metric}_low",
        metric=metric,
        value=numeric,
        threshold=threshold,
        severity=_severity(numeric, threshold),
        message=f"{label}{metric_label}为 {numeric:.0%}，低于诊断阈值 {threshold:.0%}",
        suggestion={
            "rewrite": "检查改写提示词是否保留原问题的核心语义和约束",
            "rag": "检查检索召回范围、排序和上下文拼接，避免无关或不完整片段进入回答",
        }.get(node, "检查该节点的输入、提示词和输出映射"),
    )


def diagnose_intermediate(intermediate: dict | None) -> dict:
    """为一次结果生成确定性节点诊断；缺失不按 0 分处理。"""
    payload = intermediate if isinstance(intermediate, dict) else {}
    nodes = payload.get("nodes") if isinstance(payload.get("nodes"), dict) else {}
    issues: list[dict] = []
    metric_issue_count = 0
    for node, item in nodes.items():
        if not isinstance(item, dict):
            issues.append(_missing_issue(str(node), "data_missing"))
            continue
        status = str(item.get("status") or "data_missing")
        if status in _DATA_STATUSES:
            issues.append(_missing_issue(str(node), status, item.get("error")))
            continue
        if node == "rewrite":
            for metric in ("semantic_similarity", "constraint_precision", "constraint_recall", "constraint_f1"):
                found = _metric_issue(node, metric, item.get(metric))
                if found:
                    issues.append(found)
                    metric_issue_count += 1
            if item.get("full_constraint_preservation") is False:
                issues.append(
                    _issue(
                        node=node,
                        code="rewrite.constraint_not_preserved",
                        message="改写没有完整保留标准约束",
                        suggestion="逐项检查日期、数字、实体、否定和限定条件是否被保留",
                        severity="high",
                        metric="full_constraint_preservation",
                        value=0.0,
                        threshold=1.0,
                    )
                )
                metric_issue_count += 1
        elif node == "intent" and item.get("correct") is False:
            issues.append(
                _issue(
                    node=node,
                    code="intent.classification_mismatch",
                    message=f"意图分类错误：标准为“{_bounded_text(item.get('reference'), 120)}”，实际为“{_bounded_text(item.get('predicted'), 120)}”",
                    suggestion="检查意图标签定义、边界样本和分类提示词，优先补充易混淆意图的对比例子",
                    severity="high",
                )
            )
            metric_issue_count += 1
        elif node == "rag":
            metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
            for metric in ("context_precision", "context_recall", "faithfulness", "answer_relevancy"):
                found = _metric_issue(node, metric, metrics.get(metric))
                if found:
                    issues.append(found)
                    metric_issue_count += 1
    missing_count = sum(1 for item in issues if item["code"].split(".")[-1] in _DATA_STATUSES)
    if metric_issue_count:
        status = "issues_found"
    elif missing_count:
        status = "data_missing"
    else:
        status = "ok"
    return {
        "status": status,
        "issues": issues,
        "issue_count": len(issues),
        "affected_nodes": sorted({item["node"] for item in issues}),
    }


def _extract_json(text: str) -> dict | None:
    content = str(text or "").strip()
    candidates: list[str] = []
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        candidates.append(fenced.group(1))
    candidates.append(content)
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except (TypeError, ValueError):
            continue
        if isinstance(value, dict):
            return value
    start = content.find("{")
    if start >= 0:
        try:
            value, _ = json.JSONDecoder().raw_decode(content[start:])
        except (TypeError, ValueError):
            return None
        return value if isinstance(value, dict) else None
    return None


def _llm_explanation(raw: str, allowed_nodes: set[str]) -> dict:
    payload = _extract_json(raw)
    if not payload:
        raise ValueError("模型返回的诊断建议不是合法 JSON")
    recommendations: list[dict] = []
    value = payload.get("recommendations")
    if value is not None and not isinstance(value, list):
        raise ValueError("recommendations 必须是数组")
    for item in (value or [])[:8]:
        if not isinstance(item, dict):
            continue
        node = str(item.get("node") or "").strip().lower()
        if node not in allowed_nodes:
            continue
        priority = str(item.get("priority") or "medium").strip().lower()
        if priority not in {"high", "medium", "low"}:
            priority = "medium"
        action = _bounded_text(item.get("action"), 500)
        rationale = _bounded_text(item.get("rationale"), 700)
        if action:
            recommendations.append({"node": node, "priority": priority, "action": action, "rationale": rationale})
    return {
        "status": "generated",
        "summary": _bounded_text(payload.get("summary"), 1000) or "模型未提供汇总说明",
        "recommendations": recommendations,
    }


def _diagnosis_prompt(sample: dict, result: dict, intermediate: dict, diagnosis: dict) -> str:
    data = {
        "question": sample.get("question"),
        "gold_answer": sample.get("gold_answer"),
        "actual_answer": result.get("answer"),
        "node_outputs": result.get("node_outputs"),
        "retrieved": result.get("retrieved"),
        "intermediate_scores": intermediate,
        "rule_diagnosis": diagnosis,
    }
    encoded = json.dumps(data, ensure_ascii=False, default=str)
    return f"""你是评测平台的中间节点诊断助手。请只根据下面的评测数据解释异常并提出可执行优化建议，不要修改分数，不要臆造未提供的事实。建议应针对节点实现或提示词调优，不要建议直接修改标准答案。\n\n<evaluation_data>\n{encoded[:14000]}\n</evaluation_data>\n\n请只输出合法 JSON：{{\"summary\":\"整体解释\",\"recommendations\":[{{\"node\":\"rewrite|intent|rag\",\"priority\":\"high|medium|low\",\"action\":\"建议动作\",\"rationale\":\"依据\"}}]}}"""


def explain_intermediate(sample: dict, result: dict, intermediate: dict) -> dict:
    """规则诊断必定返回；只有指标异常才额外请求 LLM。"""
    diagnosis = diagnose_intermediate(intermediate)
    explanation: dict
    if diagnosis["status"] == "ok":
        explanation = {"status": "not_needed", "summary": "已选中间节点指标均达到诊断阈值", "recommendations": []}
    elif diagnosis["status"] == "data_missing":
        explanation = {"status": "data_missing", "summary": "缺少中间节点评测所需数据，暂不生成模型建议", "recommendations": []}
    elif not getattr(settings, "llm_api_base", "") or str(getattr(settings, "llm_api_key", "") or "").startswith("sk-xxx"):
        explanation = {"status": "unavailable", "summary": "规则已定位异常，但优化解释模型未配置", "recommendations": []}
    else:
        try:
            nodes = set((intermediate.get("nodes") or {}).keys())
            explanation = _llm_explanation(
                call(_diagnosis_prompt(sample, result, intermediate, diagnosis), temperature=0.0, max_tokens=settings.llm_max_tokens),
                nodes,
            )
        except (LLMError, ValueError) as exc:
            explanation = {"status": "error", "summary": f"规则已定位异常，但模型解释失败：{_bounded_text(exc, 300)}", "recommendations": []}
        except Exception as exc:  # noqa: BLE001 — 单题建议失败不阻断评测
            explanation = {"status": "error", "summary": f"规则已定位异常，但模型解释失败：{_bounded_text(exc, 300)}", "recommendations": []}
    return {**diagnosis, "explanation": explanation}


def aggregate_intermediate_diagnosis(results: list[dict]) -> dict:
    """汇总单题诊断，保留规则问题和模型建议的可追溯计数。"""
    diagnoses = []
    for result in results:
        value = (result.get("scores") or {}).get("intermediate", {}).get("diagnosis")
        if isinstance(value, dict):
            diagnoses.append(value)
    if not diagnoses:
        return {"status": "data_missing", "affected_cases": 0, "issue_count": 0, "top_issues": [], "recommendations": [], "llm_generated_count": 0}
    issue_counter: Counter[tuple[str, str, str, str]] = Counter()
    issue_values: dict[tuple[str, str, str, str], dict] = {}
    rec_counter: Counter[tuple[str, str, str]] = Counter()
    rec_values: dict[tuple[str, str, str], dict] = {}
    affected_cases = 0
    issue_count = 0
    llm_generated_count = 0
    for diagnosis in diagnoses:
        issues = diagnosis.get("issues") or []
        if diagnosis.get("status") == "issues_found":
            affected_cases += 1
        issue_count += len(issues)
        for issue in issues:
            key = (str(issue.get("node") or ""), str(issue.get("code") or ""), str(issue.get("message") or ""), str(issue.get("suggestion") or ""))
            issue_counter[key] += 1
            issue_values[key] = issue
        explanation = diagnosis.get("explanation") or {}
        if explanation.get("status") == "generated":
            llm_generated_count += 1
        for recommendation in explanation.get("recommendations") or []:
            key = (str(recommendation.get("node") or ""), str(recommendation.get("action") or ""), str(recommendation.get("rationale") or ""))
            rec_counter[key] += 1
            rec_values[key] = recommendation
    top_issues = []
    for key, count in issue_counter.most_common(10):
        top_issues.append({**issue_values[key], "count": count})
    recommendations = []
    for key, count in rec_counter.most_common(10):
        recommendations.append({**rec_values[key], "count": count})
    has_metric_issues = bool(top_issues) and any(not item["code"].split(".")[-1] in _DATA_STATUSES for item in top_issues)
    status = "issues_found" if has_metric_issues else "data_missing"
    if not top_issues and all(item.get("status") == "ok" for item in diagnoses):
        status = "ok"
    return {
        "status": status,
        "affected_cases": affected_cases,
        "issue_count": issue_count,
        "top_issues": top_issues,
        "recommendations": recommendations,
        "llm_generated_count": llm_generated_count,
    }
