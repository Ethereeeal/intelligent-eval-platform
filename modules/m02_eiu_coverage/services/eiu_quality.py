"""EIU 候选质量检查与跨 Block 证据组装。

切块只承担定位和证据承载，不再被当作 EIU 边界。规则抽取的结果均先作为候选，
本模块以可解释的确定性检查给出 verified / needs_review / rejected 状态；复杂项
后续可再接入批量 LLM 复核，而不影响当前快速解析链路。
"""
from __future__ import annotations

import re
from collections import defaultdict


_ARTICLE_RE = re.compile(r"第[一二三四五六七八九十百千零〇两0-9]+条")
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?%?")
_SPACE_RE = re.compile(r"[\s，。；：、“”‘’（）()《》]+")
_DEICTIC_RE = re.compile(r"上述|前述|下述|该等|其修订|前款|后款|本款|以下情形|相关要求")
_PREDICATE_RE = re.compile(
    r"应当|必须|不得|禁止|可以|可由|负责|是指|包括|适用|不适用|达到|超过|低于|高于|不少于|不超过|按照|执行|办理"
)
_MODAL_RE = re.compile(r"应当|必须|不得|禁止|可以|负责|是指|适用|不适用")
_TITLE_LIKE_RE = re.compile(
    r"^(?:附件|附录|目录|第[一二三四五六七八九十百千零〇两0-9]+[章节])(?:\s|$)"
    r"|^(?:.{0,60})(?:办法|规程|细则|指引|通知)(?:[（(].{0,20}[）)])?$"
)


def _normalize(value: str) -> str:
    return _SPACE_RE.sub("", value or "").lower()


def _check(status: str, reasons: list[str]) -> dict:
    score = {"pass": 1.0, "warning": 0.5, "fail": 0.0}[status]
    return {"status": status, "score": score, "reasons": reasons}


class EiuQualityEvaluator:
    """在单文档范围内解析引用、组装证据并检查候选 EIU。"""

    def __init__(self, blocks: list[dict]) -> None:
        self.blocks = blocks
        self.by_id = {int(block["block_id"]): block for block in blocks}
        self.position = {int(block["block_id"]): i for i, block in enumerate(blocks)}
        self.article_index: dict[str, list[int]] = defaultdict(list)
        for block in blocks:
            searchable = f"{block.get('section_path') or ''} {block.get('block_text') or ''}"
            for article in set(_ARTICLE_RE.findall(searchable[:240])):
                self.article_index[article].append(int(block["block_id"]))

    def annotate(self, item: dict, source_block: dict) -> dict:
        """返回带证据链、四项检查和质量状态的新字典。"""
        result = dict(item)
        direct_id = int(source_block["block_id"])
        evidence: list[tuple[int, str]] = [(direct_id, "direct")]
        source_text = str(source_block.get("block_text") or "")
        statement = str(result.get("statement") or "").strip()

        for article in set(_ARTICLE_RE.findall(f"{statement} {source_text}")):
            for block_id in self.article_index.get(article, []):
                if block_id != direct_id:
                    evidence.append((block_id, "reference"))

        parent_id = source_block.get("parent_block_id")
        if parent_id and int(parent_id) in self.by_id:
            evidence.append((int(parent_id), "parent"))

        # “前款/上述/相关要求”等指代只能启发式补邻接上下文，仍必须进入人工复核。
        if _DEICTIC_RE.search(f"{statement} {source_text}"):
            index = self.position.get(direct_id, 0)
            if index > 0:
                previous = self.blocks[index - 1]
                if previous.get("block_type") != "title":
                    evidence.append((int(previous["block_id"]), "context"))

        deduped: list[tuple[int, str]] = []
        seen: set[int] = set()
        for block_id, role in evidence:
            if block_id in seen or block_id not in self.by_id:
                continue
            seen.add(block_id)
            deduped.append((block_id, role))

        result["evidence_blocks"] = [block_id for block_id, _ in deduped]
        result["evidence_details"] = [
            {
                "block_id": block_id,
                "role": role,
                "section_path": self.by_id[block_id].get("section_path"),
                "text": str(self.by_id[block_id].get("block_text") or "")[:500],
            }
            for block_id, role in deduped
        ]

        checks = self._evaluate(statement, source_text, deduped)
        complexity = self._complexity(statement, deduped)
        result["quality_checks"] = checks
        result["quality_score"] = round(
            sum(check["score"] for check in checks.values()) / len(checks), 4
        )
        result["complexity_level"] = complexity["level"]
        result["complexity_score"] = complexity["score"]
        result["complexity_factors"] = complexity["factors"]
        if not result.get("is_questionable", True):
            result["quality_status"] = "rejected"
        elif all(check["status"] == "pass" for check in checks.values()):
            result["quality_status"] = "verified"
        else:
            result["quality_status"] = "needs_review"
        return result

    def _complexity(
        self,
        statement: str,
        evidence: list[tuple[int, str]],
    ) -> dict:
        """以可追溯的规则评估候选声明的理解与出题复杂度（1-5 分）。"""
        clause_count = max(1, len([part for part in re.split(r"[。；！？]", statement) if part.strip()]))
        predicate_count = len(_PREDICATE_RE.findall(statement))
        numeric_count = len(_NUMBER_RE.findall(statement))
        supporting_count = sum(1 for _, role in evidence if role in {"reference", "context"})
        has_cross_reference = bool(_DEICTIC_RE.search(statement) or supporting_count)

        score = 1
        factors: list[str] = []
        if clause_count > 1:
            score += 1
            factors.append(f"包含 {clause_count} 个语义分句")
        if predicate_count > 1:
            score += 1
            factors.append(f"包含 {predicate_count} 个规则或条件谓词")
        if numeric_count:
            score += 1
            factors.append(f"包含 {numeric_count} 个量化约束")
        if has_cross_reference:
            score += 1
            factors.append("需要结合关联条款或上下文理解")
        score = min(score, 5)
        level = "L1" if score <= 2 else "L2" if score <= 4 else "L3"
        if not factors:
            factors.append("单一直接规则，无额外条件或跨段依赖")
        return {
            "level": level,
            "score": score,
            "factors": {
                "clause_count": clause_count,
                "predicate_count": predicate_count,
                "numeric_count": numeric_count,
                "supporting_evidence_count": supporting_count,
                "has_cross_reference": has_cross_reference,
                "reasons": factors,
            },
        }

    def _evaluate(
        self,
        statement: str,
        source_text: str,
        evidence: list[tuple[int, str]],
    ) -> dict[str, dict]:
        evidence_text = " ".join(
            str(self.by_id[block_id].get("block_text") or "") for block_id, _ in evidence
        )

        fidelity_reasons: list[str] = []
        normalized_statement = _normalize(statement)
        normalized_evidence = _normalize(evidence_text)
        if not normalized_statement or normalized_statement not in normalized_evidence:
            fidelity_reasons.append("声明不是证据原文的直接子串，需核对是否改写或补写")
        missing_numbers = [n for n in _NUMBER_RE.findall(statement) if n not in evidence_text]
        if missing_numbers:
            fidelity_reasons.append(f"数字未在证据中出现：{', '.join(missing_numbers)}")
        fidelity = _check("pass" if not fidelity_reasons else "warning", fidelity_reasons)

        completeness_reasons: list[str] = []
        deictic = sorted(set(_DEICTIC_RE.findall(statement)))
        if deictic:
            completeness_reasons.append(f"存在依赖上下文的指代：{', '.join(deictic)}")
        unresolved_articles = [
            article for article in set(_ARTICLE_RE.findall(statement))
            if not self.article_index.get(article)
        ]
        if unresolved_articles:
            completeness_reasons.append(f"未解析到引用条款：{', '.join(unresolved_articles)}")
        completeness = _check("pass" if not completeness_reasons else "warning", completeness_reasons)

        atomicity_reasons: list[str] = []
        modal_count = len(_MODAL_RE.findall(statement))
        if len(statement) > 160:
            atomicity_reasons.append("声明超过 160 字，可能包含多个可独立判定的事实")
        if modal_count > 1:
            atomicity_reasons.append(f"检测到 {modal_count} 个规范谓词，可能需要继续拆分")
        if "；" in statement or statement.count("：") > 1:
            atomicity_reasons.append("存在复合分句结构")
        atomicity = _check("pass" if not atomicity_reasons else "warning", atomicity_reasons)

        testability_reasons: list[str] = []
        if len(statement) < 8:
            testability_reasons.append("内容过短，无法形成稳定判定")
        if _TITLE_LIKE_RE.match(statement):
            testability_reasons.append("内容疑似标题或附件标识")
        if not (_PREDICATE_RE.search(statement) or _NUMBER_RE.search(statement)):
            testability_reasons.append("缺少可判定谓词或量化条件")
        testability = _check("pass" if not testability_reasons else "warning", testability_reasons)

        return {
            "fidelity": fidelity,
            "completeness": completeness,
            "atomicity": atomicity,
            "testability": testability,
        }
