"""分层指标体系（BRD §9.2 FR-METRIC-001~004）。

- 数据集自身质量（FR-METRIC-001）：由 m02/m04 计算，本模块引用；
- 检索指标（FR-METRIC-002）：Evidence Recall@K 等（待测系统返回检索轨迹时）；
- 答案指标（FR-METRIC-003）：EM / 语义相似度 / 拒答正确率；
- 运行指标（FR-METRIC-004）：耗时 / Token / 成本 / 错误率，按难度与维度分组。
"""
from __future__ import annotations

from collections import Counter

from modules.m05_dataset_lifecycle.services.scoring import score_answer


def score_case(sample: dict, result: dict) -> dict:
    """单题分层评分：短答案规范化精确匹配，长答案语义相似度（FR-DS-SRC-003）。"""
    gold = str(sample.get("gold_answer") or "").strip()
    answer = str((result or {}).get("answer") or "").strip()
    error = (result or {}).get("error")
    usage = (result or {}).get("usage") or {}
    if error:
        return {
            "em": None,
            "score": None,
            "method": None,
            "refusal_ok": None,
            "latency_ms": usage.get("time_ms"),
            "tokens": usage.get("tokens"),
            "cost": usage.get("cost"),
            "error": error,
        }
    if not gold:
        return {
            "em": None,
            "score": None,
            "method": None,
            "refusal_ok": None,
            "latency_ms": usage.get("time_ms"),
            "tokens": usage.get("tokens"),
            "cost": usage.get("cost"),
            "error": None,
        }
    use_semantic = len(gold) > 30
    scoring = score_answer(answer, gold, use_semantic=use_semantic)
    return {
        "em": scoring["exact_match"],
        "score": scoring["score"],
        "method": scoring["method"],
        "refusal_ok": None,
        "latency_ms": usage.get("time_ms"),
        "tokens": usage.get("tokens"),
        "cost": usage.get("cost"),
        "error": None,
    }


def aggregate(results: list[dict]) -> dict:
    """运行结果汇总：通过率、按难度/维度分组、耗时成本、错误率。"""
    scored = [r for r in results if r.get("scores") and r["scores"].get("score") is not None]
    errors = [r for r in results if r.get("status") == "error"]
    passed = [r for r in scored if r["scores"].get("score", 0) >= 0.5]
    by_difficulty: dict[str, dict] = {}
    by_dimension: dict[str, dict] = {}
    total_latency = 0
    total_tokens = 0
    total_cost = 0.0
    for r in results:
        scores = r.get("scores") or {}
        total_latency += scores.get("latency_ms") or 0
        total_tokens += scores.get("tokens") or 0
        total_cost += scores.get("cost") or 0.0
        bucket = by_difficulty.setdefault(
            r.get("difficulty") or "unknown", {"total": 0, "passed": 0}
        )
        bucket["total"] += 1
        if r.get("scores") and r["scores"].get("score", 0) >= 0.5:
            bucket["passed"] += 1
        dim = r.get("dimension") or "none"
        dim_bucket = by_dimension.setdefault(dim, {"total": 0, "passed": 0})
        dim_bucket["total"] += 1
        if r.get("scores") and r["scores"].get("score", 0) >= 0.5:
            dim_bucket["passed"] += 1
    return {
        "total": len(results),
        "scored": len(scored),
        "passed": len(passed),
        "passed_rate": round(len(passed) / len(scored), 4) if scored else None,
        "error_count": len(errors),
        "error_rate": round(len(errors) / len(results), 4) if results else None,
        "diagnosis_distribution": dict(Counter(r.get("diagnosis") for r in results if r.get("diagnosis"))),
        "by_difficulty": by_difficulty,
        "by_dimension": by_dimension,
        "total_latency_ms": total_latency,
        "total_tokens": total_tokens,
        "total_cost": round(total_cost, 4),
    }
