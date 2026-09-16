"""分层指标体系（BRD §9.2 FR-METRIC-001~004）。

- 数据集自身质量（FR-METRIC-001）：由 m02/m04 计算，本模块引用；
- 检索指标（FR-METRIC-002）：Evidence Recall@K 等（待测系统返回检索轨迹时）；
- 答案指标（FR-METRIC-003）：EM / 语义相似度 / 规则评测 / 可选 LLM-as-a-Judge / 拒答正确率；
- 运行指标（FR-METRIC-004）：耗时 / Token / 成本 / 错误率，按难度与维度分组。
"""
from __future__ import annotations

from collections import Counter

from modules.m05_dataset_lifecycle.services.scoring import score_answer
from modules.m08_auto_evaluation.services.intermediate_metrics import (
    aggregate_intermediate,
    normalize_intermediate_config,
)
from modules.m08_auto_evaluation.services.judge import evaluate_judge, normalize_judge_config
from modules.m08_auto_evaluation.services.method_config import (
    METHOD_LABELS,
    METHOD_STANDARD_LABELS,
    normalize_evaluation_selection,
)
from modules.m08_auto_evaluation.services.rules import evaluate_rules
from modules.m08_auto_evaluation.services.text_metrics import (
    BLEU_PARAMETERS,
    ROUGE_L_PARAMETERS,
    score_reference_metric,
)


def score_case(
    sample: dict,
    result: dict,
    judge_config: dict | None = None,
    evaluation_methods: list[str] | None = None,
    task_profile: str = "question_answering",
) -> dict:
    """单题分层评分：答案、规则与 LLM Judge 独立计算。"""
    gold = str(sample.get("gold_answer") or "").strip()
    answer = str((result or {}).get("answer") or "").strip()
    error = (result or {}).get("error")
    usage = (result or {}).get("usage") or {}
    legacy = evaluation_methods is None
    selection = normalize_evaluation_selection(
        task_profile,
        evaluation_methods,
        legacy_judge_enabled=bool((judge_config or {}).get("enabled")),
    )
    methods = selection["evaluation_methods"]
    rule_score = None
    if not error and "rules" in methods:
        rule_score = evaluate_rules(sample, answer)
        if rule_score is None and not legacy:
            rule_score = {
                "method": "rules",
                "status": "data_missing",
                "score": None,
                "passed": None,
                "reason": "评测样本未提供 must_have_points 或 acceptable_answers",
            }
    judge_config = dict(judge_config or {})
    judge_config["enabled"] = "llm_as_judge" in methods
    judge_score = None if error else evaluate_judge(sample, result or {}, judge_config)
    reference_metrics = {
        method: score_reference_metric(method, sample, answer)
        for method in ("bleu", "rouge_l")
        if method in methods and not error
    }
    if error:
        if not legacy and "rules" in methods:
            rule_score = {
                "method": "rules",
                "status": "error",
                "score": None,
                "passed": None,
                "reason": "目标智能体调用失败，未执行规则评测",
            }
        if not legacy and "llm_as_judge" in methods:
            judge_score = {
                "method": "llm_as_judge",
                "status": "error",
                "score": None,
                "passed": None,
                "reason": "目标智能体调用失败，未执行 Judge 评测",
            }
        reference_metrics = {
            method: {
                "method": method,
                "status": "error",
                "score": None,
                "reason": "目标智能体调用失败，未执行文本指标",
                "parameters": dict(BLEU_PARAMETERS if method == "bleu" else ROUGE_L_PARAMETERS),
            }
            for method in ("bleu", "rouge_l")
            if method in methods
        }
    if error:
        scores = {
            "em": None,
            "score": None,
            "method": None,
            "rule": rule_score,
            "judge": judge_score,
            "refusal_ok": None,
            "latency_ms": usage.get("time_ms"),
            "tokens": usage.get("tokens"),
            "cost": usage.get("cost"),
            "error": error,
        }
        scores.update(reference_metrics)
        if "answer_comparison" in methods:
            scores["answer_comparison"] = {"status": "error", "score": None}
        return scores
    if "answer_comparison" not in methods or not gold:
        scores = {
            "em": None,
            "score": None,
            "method": None,
            "rule": rule_score,
            "judge": judge_score,
            "refusal_ok": None,
            "latency_ms": usage.get("time_ms"),
            "tokens": usage.get("tokens"),
            "cost": usage.get("cost"),
            "error": None,
        }
        if "answer_comparison" in methods:
            scores["answer_comparison"] = {
                "status": "data_missing",
                "score": None,
                "reason": "评测样本未提供标准答案",
            }
        scores.update(reference_metrics)
        return scores
    use_semantic = len(gold) > 30
    scoring = score_answer(answer, gold, use_semantic=use_semantic)
    scores = {
        "em": scoring["exact_match"],
        "score": scoring["score"],
        "method": scoring["method"],
        "rule": rule_score,
        "judge": judge_score,
        "refusal_ok": None,
        "latency_ms": usage.get("time_ms"),
        "tokens": usage.get("tokens"),
        "cost": usage.get("cost"),
        "error": None,
        "answer_comparison": {
            "status": "scored",
            "method": scoring["method"],
            "score": scoring["score"],
            "exact_match": scoring["exact_match"],
        },
    }
    scores.update(reference_metrics)
    return scores


def aggregate(
    results: list[dict],
    intermediate_config: dict | None = None,
    judge_config: dict | None = None,
    task_profile: str | None = None,
    evaluation_methods: list[str] | None = None,
) -> dict:
    """运行结果汇总：主评分、规则、Judge、按难度/维度分组、耗时成本和错误率。"""
    scored = [r for r in results if r.get("scores") and r["scores"].get("score") is not None]
    rule_scored = []
    judge_scored = []
    for result in results:
        rule = (result.get("scores") or {}).get("rule") or {}
        if rule.get("score") is not None:
            rule_scored.append(result)
        judge = (result.get("scores") or {}).get("judge") or {}
        if judge.get("status") == "scored" and judge.get("score") is not None:
            judge_scored.append(result)
    errors = [r for r in results if r.get("status") == "error"]
    passed = [r for r in scored if r["scores"].get("score", 0) >= 0.5]
    rule_passed = [
        result for result in rule_scored
        if ((result.get("scores") or {}).get("rule") or {}).get("score", 0) >= 0.5
    ]
    judge_passed = [
        result for result in judge_scored
        if ((result.get("scores") or {}).get("judge") or {}).get("passed") is True
    ]
    by_difficulty: dict[str, dict] = {}
    by_dimension: dict[str, dict] = {}
    total_latency = 0
    total_tokens = 0
    total_cost = 0.0
    for r in results:
        scores = r.get("scores") or {}
        score = scores.get("score")
        total_latency += scores.get("latency_ms") or 0
        total_tokens += scores.get("tokens") or 0
        total_cost += scores.get("cost") or 0.0
        bucket = by_difficulty.setdefault(
            r.get("difficulty") or "unknown", {"total": 0, "passed": 0}
        )
        bucket["total"] += 1
        if score is not None and score >= 0.5:
            bucket["passed"] += 1
        dim = r.get("dimension") or "none"
        dim_bucket = by_dimension.setdefault(dim, {"total": 0, "passed": 0})
        dim_bucket["total"] += 1
        if score is not None and score >= 0.5:
            dim_bucket["passed"] += 1
    normalized_intermediate = normalize_intermediate_config(intermediate_config)
    normalized_judge = normalize_judge_config(judge_config) if judge_config is not None else None
    selection = normalize_evaluation_selection(
        task_profile,
        evaluation_methods,
        legacy_judge_enabled=bool(normalized_judge and normalized_judge["enabled"]),
    )
    reference_metric_summaries: dict[str, dict] = {}
    for method in ("bleu", "rouge_l"):
        if method not in selection["evaluation_methods"]:
            continue
        method_results = [((result.get("scores") or {}).get(method) or {}) for result in results]
        values = [
            float(item["score"])
            for item in method_results
            if item.get("status") == "scored" and item.get("score") is not None
        ]
        statuses = Counter(item.get("status", "data_missing") for item in method_results)
        status = (
            "scored" if values else "error" if statuses.get("error")
            else "unavailable" if statuses.get("unavailable") else "data_missing"
        )
        reference_metric_summaries[method] = {
            "label": METHOD_LABELS[method],
            "standard": METHOD_STANDARD_LABELS[method],
            "status": status,
            "score": round(sum(values) / len(values), 4) if values else None,
            "scored": len(values),
            "total": len(results),
            "data_missing": statuses.get("data_missing", 0),
            "unavailable": statuses.get("unavailable", 0),
            "errors": statuses.get("error", 0),
        }
    return {
        "total": len(results),
        "task_profile": selection["task_profile"],
        "evaluation_methods": selection["evaluation_methods"],
        "scored": len(scored),
        "passed": len(passed),
        "passed_rate": round(len(passed) / len(scored), 4) if scored else None,
        "rule_scored": len(rule_scored),
        "rule_passed": len(rule_passed),
        "rule_passed_rate": round(len(rule_passed) / len(rule_scored), 4) if rule_scored else None,
        "judge_enabled": bool(normalized_judge and normalized_judge["enabled"]),
        "judge_scored": len(judge_scored),
        "judge_passed": len(judge_passed),
        "judge_passed_rate": round(len(judge_passed) / len(judge_scored), 4) if judge_scored else None,
        "error_count": len(errors),
        "error_rate": round(len(errors) / len(results), 4) if results else None,
        "diagnosis_distribution": dict(Counter(r.get("diagnosis") for r in results if r.get("diagnosis"))),
        "by_difficulty": by_difficulty,
        "by_dimension": by_dimension,
        "total_latency_ms": total_latency,
        "total_tokens": total_tokens,
        "total_cost": round(total_cost, 4),
        "reference_metrics": reference_metric_summaries,
        "intermediate": aggregate_intermediate(
            results,
            normalized_intermediate["nodes"],
        ) if normalized_intermediate["enabled"] else None,
    }
