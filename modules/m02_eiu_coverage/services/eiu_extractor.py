"""M02 — EIU 抽取核心逻辑（SPEC §5.3 / §5.4 / §8）。

逐 Block 调用 LLM 抽取可评测信息单元，复用 M01 的 doc_update_job 反馈进度：
  progress = 已处理段落 Block 数 / 总段落 Block 数 × 100
无实质内容的 Block 写入排除记录（is_questionable=false + exclusion_reason），
保证"实质 Block 对账率"可达 100%（SPEC §6.4 / §6.3）。

LLM 不可用（未安装 openai / API Key 为占位符）时，自动降级为确定性规则抽取
（deterministic_extract），保证离线环境可完成全链路演示与数据质量验收。
"""
from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Any

from modules.m01_data_foundation.services.eiu_indexer import EiuFaissIndex
from modules.m02_eiu_coverage.services.context_bundle import ContextBundleBuilder
from modules.m02_eiu_coverage.services.eiu_quality import EiuQualityEvaluator
from modules.m02_eiu_coverage.services.eiu_review import EiuReviewMixin
from modules.m02_eiu_coverage.services.llm_client import LLMClient, LLMError
from modules.shared.services.database import EIU_TYPES, PRIORITY_WEIGHT, DatabaseService

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "eiu_extraction.txt"
_STATEMENT_MAX = 200  # 验收 D4：statement ≤ 200 字

# 语义去重阈值：BGE 余弦相似度 ≥ 该值视为"同义知识点"，后出现的重复条标记排除
SEMANTIC_DEDUP_THRESHOLD = 0.90

# 过渡句 / 无实质内容关键字（标题与目录等已由 block_type 过滤，此处兜底）
_SKIP_KEYWORDS = (
    "见上文", "见下文", "详见", "见附件", "如表", "如下表", "如下图", "见图",
    "（完）", "（续）", "承前", "接上页", "以下略", "以下同", "页眉", "页脚",
    "目录", "引用本文", "本节导读", "本章导读",
)

_SENTENCE_SPLIT = re.compile(r"[。；;\n]+")
_NUMBERING_PREFIX = re.compile(
    r"^(?:[（(]\s*[一二三四五六七八九十\d]+\s*[）)]|[①②③④⑤⑥⑦⑧⑨⑩]+|\d+\s*[、.．])"
)
_REVIEW_PREDICATE_RE = re.compile(
    r"应当|必须|不得|禁止|不准|不允许|仅接受|不接受|不可|不得为|仅限|限于|应为|"
    r"可以|负责|是指|适用|不适用|施行|生效|实施"
)
_REFERENCE_RE = re.compile(
    r"上述|前述|下述|该等|其修订|前款|后款|本款|以下情形|相关要求|"
    r"第[一二三四五六七八九十百千零〇两0-9]+条"
)
_EXCEPTION_RE = re.compile(r"除非|除外|例外|但(?:是)?|可放宽|不适用")
_LIST_RE = re.compile(r"(?:：|包括|如下|下列).{0,120}[、；]")
_YELLOW_BLOCK_LENGTH = 320
_REVIEW_ACTIONS = {"pass", "split", "merge", "complete_context", "reject", "human_review"}


# ----------------------------------------------------------------------
# 段落预处理（skip_filter，SPEC §5.4 第 1 步）
# ----------------------------------------------------------------------
def is_skippable(text: str) -> bool:
    """纯标题 / 过渡句 / 页眉页脚等无实质内容的段落直接跳过。"""
    stripped = text.strip()
    if not stripped:
        return True
    if len(stripped) <= 2:
        return True
    if re.fullmatch(r"[0-9\s\-—.·/\\|，,、]+", stripped):
        return True
    if any(keyword in stripped for keyword in _SKIP_KEYWORDS) and len(stripped) < 40:
        return True
    return False


def _clean_statement(text: str) -> str:
    """去掉编号前缀与结尾句号，得到一句话陈述。"""
    text = _NUMBERING_PREFIX.sub("", text.strip()).strip()
    text = re.sub(r"[。；;\s]+$", "", text).strip()
    return text


def _clamp_confidence(value: float | None) -> float:
    if value is None:
        return 0.8
    return max(0.0, min(1.0, float(value)))


def _truncate_statement(text: str, max_len: int = _STATEMENT_MAX) -> str:
    """按 200 字上限截断 EIU 陈述，优先在句界 / 逗号处截断。

    避免直接硬切把限定语（主体/条件/范围/期间等）拦腰截断；
    整句不超过上限时原样返回。验收 D4 仍保证 len(statement) ≤ 200。
    """
    if len(text) <= max_len:
        return text
    cut = text[:max_len]
    for boundary in ("。", "；", "！", "？", "\n"):
        idx = cut.rfind(boundary)
        if idx > 0:
            return cut[: idx + 1]
    idx = cut.rfind("，")
    if idx > 0:
        return cut[: idx + 1]
    return cut


def _default_constraints() -> dict:
    return {"主体": None, "条件": None, "范围": None, "期间": None, "币种": None, "单位": None}


def _review_action(value: object) -> str:
    action = str(value or "human_review").strip().lower()
    return action if action in _REVIEW_ACTIONS else "human_review"


def _review_evidence(context: dict, requested_ids: object, current_block_id: int) -> tuple[list[int], list[dict]]:
    """绑定文档上下文映射已解析进 Context Bundle 的证据；同一 Block 可承担多个角色。"""
    sources = context.get("evidence_sources") or []
    source_by_id: dict[int, dict] = {}
    for source in sources:
        if not isinstance(source, dict) or source.get("block_id") is None:
            continue
        block_id = int(source["block_id"])
        roles = source.get("roles") or [source.get("role") or "context"]
        entry = source_by_id.setdefault(block_id, {"block_id": block_id, "roles": []})
        entry["roles"] = sorted(set(entry["roles"]).union(str(role) for role in roles if role))
    if not source_by_id:
        source_by_id[current_block_id] = {"block_id": current_block_id, "roles": ["current"]}
    ids = requested_ids if isinstance(requested_ids, list) else []
    selected = [int(value) for value in ids if isinstance(value, int) and int(value) in source_by_id]
    if not selected:
        selected = [current_block_id]
    selected = list(dict.fromkeys(selected))
    return selected, [source_by_id[block_id] for block_id in selected]


def _context_requests(items: object) -> list[dict]:
    """收集第一轮审查提出的补证请求，限制格式和数量以避免无限扩展。"""
    if not isinstance(items, list):
        return []
    requests: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        values = item.get("context_requests") or []
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, dict):
                continue
            kind = str(value.get("kind") or "context").strip().lower()
            query = str(value.get("query") or "").strip()[:80]
            article_no = str(value.get("article_no") or "").strip()[:20]
            key = (kind, query, article_no)
            if key not in seen and (query or article_no):
                seen.add(key)
                requests.append({"kind": kind, "query": query, "article_no": article_no})
    return requests[:3]


# ----------------------------------------------------------------------
# 确定性规则抽取（offline 模式，SPEC §5.2 缺省配置下的降级实现）
# ----------------------------------------------------------------------
def _split_sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_SPLIT.split(text) if part.strip()]


def _classify(sentence: str) -> tuple[str, str] | None:
    """按优先级判定句子属于哪类 EIU（type, priority）。无实质内容返回 None。"""
    if not sentence or len(sentence) < 4:
        return None

    # prohibition（禁止事项，P0）
    if re.match(r"^(?:禁止|严禁|不准|不允许|不得)", sentence) or (
        "禁止" in sentence or "严禁" in sentence
    ):
        return "prohibition", "P0"

    # exception（例外 / 放宽，P0/P1）
    if re.search(r"除非|除外|例外|可放宽|可不(?:受|适用|按|计)|但(?:是)?.{0,6}(?:可以|允许|不受)", sentence):
        return "exception", "P0"

    # threshold（数值 / 百分比 / 上下限，P0）
    # 兼容两种语序："不得超过70%"（限定词在前）与 "70%以上"（数值在前）
    if re.search(
        r"(?:不超过|不得超过|不得低于|不得高于|不得少于|不低于|不高于|上限|下限|控制在|最高|最低)"
        r"\s*\d[\d,.]*(?:%|％|万元|亿元|元|个|户|笔|人|天|个月|年|倍)?"
        r"|\d[\d,.]*(?:%|％|万元|亿元|元|个|户|笔|人|天|个月|年|倍)?"
        r"\s*(?:以上|以下|不超过|不得超过|不得低于|不得高于|不得少于|不低于|不高于)",
        sentence,
    ):
        return "threshold", "P0"

    # date（时效，P1）
    if re.search(r"(?:\d{4}年\d{1,2}月\d{1,2}日|\d{1,2}月\d{1,2}日).{0,10}(?:施行|生效|执行|实施|截止)|(?:自|从).{0,12}(?:起施行|起生效|起实施)", sentence):
        return "date", "P1"

    # formula（公式 / 计算，P1）
    if "=" in sentence or re.search(r"率\s*=|公式|除以|乘以|计算方式|计算公式|按下列公式", sentence):
        return "formula", "P1"

    # definition（定义，P1）
    if re.search(r"是指|系指|指.{0,4}(?:而言|的)|定义为|定义如下|包括.{0,12}(?:等|几类|下列)", sentence):
        return "definition", "P1"

    # rule（主流程规则，P1）
    if re.search(r"应当|应(?:当|该|按|于|及时|优先|在|自|从|提供|取得)|必须|须(?:经|在|于|按|取得|报)|原则上|要求.{0,4}(?:满足|符合|执行|遵守)", sentence):
        return "rule", "P1"

    # process（流程顺序，P1）
    if re.search(r"流程|步骤|依次|顺序|先后|先.{0,8}(?:再|然后).{0,8}(?:后|最终)|办理程序|操作流程|审批流程", sentence):
        return "process", "P1"

    # metric（指标值，P2）
    if re.search(r"\d[\d,]*(?:\.\d+)?\s*(?:万元|亿元|元|户|笔|人|%)", sentence) and re.search(
        r"(?:达到|为|计|累计|总额|余额|金额|人数|户数|增长率|净利润|营业收入)", sentence
    ):
        return "metric", "P2"

    # change（变更 / 新旧更替，P1）
    if re.search(r"调整(?:为|至|到)?|修订|改版|新版|旧版|由.{0,10}(?:改为|调整为|变更为|提高|降低|提高到|降低至)|较.{0,4}(?:版|年度)", sentence):
        return "change", "P1"

    # 兜底：一般说明（P2），避免有效业务信息被漏抽
    if len(sentence) >= 8:
        return "rule", "P2"
    return None


def _constraints_for(sentence: str) -> dict:
    """从句子中启发式提取约束字段（主体 / 条件 / 期间 / 币种 / 单位）。"""
    constraints = _default_constraints()
    for unit in ("万元", "亿元", "元", "%", "％", "倍", "人", "户", "笔", "天", "个月"):
        if unit in sentence:
            constraints["单位"] = unit
            break
    period = re.search(r"(\d{4}年)", sentence)
    if period:
        constraints["期间"] = period.group(1)
    condition = re.search(r"(.{2,30}?(?:时|的|的情况下|条件下|如果|当))", sentence)
    if condition and len(condition.group(1)) <= 40:
        constraints["条件"] = condition.group(1)
    for currency in ("人民币", "美元", "欧元", "港币", "日元"):
        if currency in sentence:
            constraints["币种"] = currency
            break
    subject = re.match(
        r"^([^，,。；;]{2,18}?(?:公司|银行|企业|单位|机构|贷款人|借款人|支行|客户|小微企业|担保机构|员工))",
        sentence,
    )
    if subject:
        constraints["主体"] = subject.group(1)
    if constraints["主体"] is None:
        generic_subject = re.match(
            r"^([^，,。；;]{2,24}?)(?=(?:应当|必须|不得|禁止|严禁|不准|不允许|仅接受|不接受|可以|自|于).{0,12}(?:接受|提供|开立|办理|提交|审核|执行|遵守|满足|符合|控制|报送|留存|使用|支付|实施|施行|生效))",
            sentence,
        )
        if generic_subject:
            constraints["主体"] = generic_subject.group(1)
    return constraints


_MODALITY_RE = re.compile(r"(应当|必须|不得|禁止|严禁|不准|不允许|仅接受|不接受|可以|可|应)")
_CLAIM_PREDICATE_RE = re.compile(r"(接受|提供|开立|办理|提交|审核|执行|遵守|满足|符合|控制|报送|留存|使用|支付|实施|施行|生效)")


def _claim_fields(statement: str, constraints: dict | None = None) -> dict:
    """以可解释的轻量规则填充结构化知识点字段；无法稳定判断的字段保留为空。"""
    constraints = constraints or {}
    modality_match = _MODALITY_RE.search(statement)
    modality = modality_match.group(1) if modality_match else None
    before = statement[:modality_match.start()].strip("，、：: ") if modality_match else ""
    after = statement[modality_match.end():].strip("，、：: ") if modality_match else statement
    predicate_match = _CLAIM_PREDICATE_RE.search(after)
    predicate = predicate_match.group(1) if predicate_match else None
    object_text = after[predicate_match.end():].strip("，、：: ") if predicate_match else after
    subject = constraints.get("主体") or (before if 2 <= len(before) <= 32 else None)
    qualifiers = {key: value for key, value in constraints.items() if value not in (None, "")}
    return {
        "subject": subject,
        "predicate": predicate,
        "object": object_text or None,
        "modality": modality,
        "qualifiers": qualifiers or None,
    }


def deterministic_extract(text: str) -> list[dict]:
    """离线确定性抽取：逐句分类生成 EIU，批内按 statement 去重。"""
    results: list[dict] = []
    seen: set[str] = set()
    for sentence in _split_sentences(text):
        if is_skippable(sentence):
            continue
        classification = _classify(sentence)
        if classification is None:
            continue
        eiu_type, priority = classification
        statement = _clean_statement(sentence)
        if not statement or statement in seen:
            continue
        seen.add(statement)
        results.append(
            {
                "statement": _truncate_statement(statement),
                "eiu_type": eiu_type,
                "content_priority": priority,
                "constraints": _constraints_for(sentence),
                "is_questionable": True,
                "exclusion_reason": None,
                "extraction_model": "offline-rule-based",
                "extraction_confidence": 0.5,
                **_claim_fields(statement, _constraints_for(sentence)),
            }
        )
    return results


def _requires_llm_review(block: dict, rule_items: list[dict]) -> bool:
    """判断规则候选是否属于黄色：需要 LLM 在局部上下文中拆分、合并或补全。

    这里刻意不把“规则已抽到结果”当作自动通过条件。黄色只发送当前 Block、
    相邻上下文和同 Block 候选，避免逐条或整篇文档调用。
    """
    return bool(_yellow_route_reasons(block, rule_items))


def _yellow_route_reasons(block: dict, rule_items: list[dict]) -> list[str]:
    """返回候选进入黄色 LLM 审查的可审计原因。"""
    text = str(block.get("block_text") or "")
    block_type = str(block.get("block_type") or "")
    reasons: list[str] = []
    if len(rule_items) != 1:
        reasons.append("一个 Block 对应多个或零个候选，不能确定性放行")
    if len(rule_items) == 1:
        candidate = rule_items[0]
        constraints = candidate.get("constraints") or {}
        if not constraints.get("主体"):
            reasons.append("未识别到显式主体，需补全或确认")
        if not candidate.get("predicate"):
            reasons.append("未识别到单一可判定谓词，需复核")
        if len(_CLAIM_PREDICATE_RE.findall(str(candidate.get("statement") or ""))) > 1:
            reasons.append("候选包含多个并列动作，需判断是否拆分")
        has_numeric_limit = bool(re.search(r"\d[\d,.]*\s*(?:%|％|万元|亿元|元|倍|户|笔|天|个月)", text))
        if has_numeric_limit and not constraints.get("单位"):
            reasons.append("存在量化值但未提取单位，需补全量化条件")
    predicate_count = len(_REVIEW_PREDICATE_RE.findall(text))
    if predicate_count > 1:
        reasons.append(f"检测到 {predicate_count} 个业务谓词，需判断拆分或合并")
    if _REFERENCE_RE.search(text):
        reasons.append("包含指代或显式条款引用，需补全上下文")
    if _EXCEPTION_RE.search(text):
        reasons.append("一般规则与例外可能混合")
    if _LIST_RE.search(text):
        reasons.append("包含列表引导或多个列表项")
    if len(text) > _YELLOW_BLOCK_LENGTH:
        reasons.append(f"Block 长度 {len(text)} 超过 {_YELLOW_BLOCK_LENGTH} 字")
    if block_type.startswith(("table", "excel")):
        reasons.append("表格类 Block 需要校验表头和单元格上下文")
    # rule/P2 是确定性抽取的兜底分类，类型/优先级并不可靠，交由 LLM 校正。
    if any(item.get("eiu_type") == "rule" and item.get("content_priority") == "P2" for item in rule_items):
        reasons.append("规则兜底分类 rule/P2，类型或优先级需复核")
    # P0 对证据完整度要求更高，默认送局部审查而非直接放行。
    if any(item.get("content_priority") == "P0" for item in rule_items):
        reasons.append("P0 候选需要全量证据复核")
    return reasons


# ----------------------------------------------------------------------
# EIU 校验 / 规范化（SPEC §5.4 第 4 步）
# ----------------------------------------------------------------------
def normalize_item(item: dict, block_id: int, extraction_model: str) -> dict | None:
    """校验并规范化一条 LLM 返回的 EIU；字段非法则返回 None（跳过该条）。"""
    if not isinstance(item, dict):
        return None
    statement = str(item.get("statement", "") or "").strip()
    if not statement:
        return None

    eiu_type = str(item.get("eiu_type", "") or "").strip()
    if eiu_type not in EIU_TYPES:
        return None  # 非法类型：跳过该条（验收 F13 容错）

    priority = str(item.get("content_priority", "P2") or "P2").strip()
    if priority not in PRIORITY_WEIGHT:
        priority = "P2"

    is_questionable = bool(item.get("is_questionable", True))
    exclusion_reason = item.get("exclusion_reason")
    if not is_questionable:
        exclusion_reason = str(exclusion_reason or "").strip() or "未说明排除原因"
    else:
        exclusion_reason = None

    constraints = item.get("constraints")
    if not isinstance(constraints, dict):
        constraints = _default_constraints()
    else:
        merged = _default_constraints()
        merged.update({k: v for k, v in constraints.items() if k in merged})
        constraints = merged

    confidence = item.get("extraction_confidence")
    try:
        confidence = float(confidence) if confidence is not None else 0.8
    except (TypeError, ValueError):
        confidence = 0.8

    return {
        "block_id": block_id,
        "statement": _truncate_statement(statement),
        "eiu_type": eiu_type,
        "content_priority": priority,
        "constraints": constraints,
        "evidence_blocks": [block_id],
        "is_questionable": is_questionable,
        "exclusion_reason": exclusion_reason,
        "extraction_model": extraction_model,
        "extraction_confidence": _clamp_confidence(confidence),
        "review_status": "candidate",
    }


def _norm(text: str) -> str:
    """归一化知识点陈述，用作精确去重 key（去编号/标点/空白/小写）。"""
    t = re.sub(r"\s+", "", text)
    t = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]", "", t)
    return t.lower()


_embedder = None


def _encode_one(text: str) -> list[float] | None:
    """BGE 编码单条 statement（query 模式）。无模型则返回 None，去重层优雅跳过。"""
    global _embedder
    if _embedder is False:
        return None
    try:
        if _embedder is None:
            from modules.m01_data_foundation.services.embedding import EmbeddingService
            _embedder = EmbeddingService()
        (vec,) = _embedder.embed_texts([text], is_query=True)
        return list(vec)
    except Exception:
        _embedder = False
        return None


def _dedup_semantic(
    items: list[dict],
    seen: list[tuple[str, list[float]]],
    faiss_idx: Any | None = None,
) -> list[dict]:
    """对一批抽出的 EIU 做语义去重（跨 Block 同义合并）。

    - 精确层：归一化 statement 与已插入者完全一致 → 重复；
    - 语义层：BGE 余弦相似度 ≥ SEMANTIC_DEDUP_THRESHOLD → 同义重复。
      faiss_idx 传入时用 FAISS 检索判重（EIU 向量索引）；否则回退线性扫描。
    重复者不入库，改为 is_questionable=False + 排除原因，仍计入对账率。
    无本地 BGE 模型时仅做精确去重，不阻断主流程。
    """
    if not items:
        return items
    out: list[dict] = []
    for it in items:
        if not it.get("is_questionable"):
            out.append(it)
            continue
        stmt = (it.get("statement") or "").strip()
        k = _norm(stmt)
        dup = False
        # 精确层：归一化 key 一致
        for seen_k, _seen_vec in seen:
            if seen_k == k:
                dup = True
                break
        # 语义层：FAISS 检索（或线性）余弦 ≥ 阈值
        if not dup:
            vec = _encode_one(stmt)
            if vec is not None:
                if faiss_idx is not None and faiss_idx.search_by_vector:
                    hits = faiss_idx.search_by_vector(vec, top_k=1)
                    if hits and hits[0].get("score", 0.0) >= SEMANTIC_DEDUP_THRESHOLD:
                        dup = True
                else:
                    for _seen_k, seen_vec in seen:
                        if seen_vec is not None:
                            sim = sum(a * b for a, b in zip(vec, seen_vec))
                            if sim >= SEMANTIC_DEDUP_THRESHOLD:
                                dup = True
                                break
        if dup:
            it = dict(it)
            it["force_needs_review"] = True
            it["route_color"] = "yellow"
            it["review_action"] = "merge"
            it["route_reasons"] = [
                *(it.get("route_reasons") or []),
                "检测到与既有知识点重复，待人工确认后合并证据",
            ]
            it["exclusion_reason"] = "与已抽取知识点语义重复（同义去重）"
        if dup:
            it.pop("exclusion_reason", None)
        out.append(it)
    return out


def exclusion_item(block: dict, reason: str) -> dict:
    """为无可抽内容 / 抽取失败的 Block 生成排除记录，保证对账率 100%（SPEC §6.4）。"""
    return {
        "block_id": block["block_id"],
        "statement": f"[排除] {reason}",
        "eiu_type": "rule",
        "content_priority": "P2",
        "constraints": _default_constraints(),
        "evidence_blocks": [block["block_id"]],
        "is_questionable": False,
        "exclusion_reason": reason[:128],
        "extraction_model": "skip-filter",
        "extraction_confidence": 0.0,
        "review_status": "candidate",
    }


# ----------------------------------------------------------------------
# 抽取服务
# ----------------------------------------------------------------------
class EiuExtractorService(EiuReviewMixin):
    _run_lock = threading.Lock()

    def __init__(self) -> None:
        self.database = DatabaseService()
        self.llm = LLMClient()
        self.system_prompt = self._load_prompt()
        # 同一条款的首次黄色审查结果按 Block 暂存，仅在当前抽取运行内复用。
        self._article_review_cache: dict[tuple[str, int], list[dict]] = {}

    @staticmethod
    def _load_prompt() -> str:
        try:
            return _PROMPT_PATH.read_text(encoding="utf-8")
        except OSError:
            return "你是一位精通银行授信政策和金融监管文件的专家。"

    def extract_corpus(
        self,
        job_id: int,
        *,
        finalize_job: bool = True,
        progress_start: int = 0,
        progress_end: int = 100,
    ) -> dict:
        """对全部文档的段落 Block 执行 EIU 抽取（后台线程调用）。

        全量重算：先清空全部旧 EIU，再逐 Block 抽取写入。

        finalize_job=False 时（重传闭环编排用）：只更新进度、不把 job 置
        completed，由编排层在版本重建完成后统一收口，保证
        parsing → eiu_extract → rebuild → done 共用一个 job。
        progress_start/progress_end：把本阶段进度映射到整体 0–100 刻度
        （编排模式传 40/90，独立调用保持 0/100）。
        """
        try:
            return self._run(
                job_id,
                finalize_job=finalize_job,
                progress_start=progress_start,
                progress_end=progress_end,
            )
        except Exception as exc:  # noqa: BLE001 — 记录失败并置 job 状态
            self.database.update_job(
                job_id, status="failed", phase="eiu_extract", message=f"EIU 抽取失败: {exc}"
            )
            return {"job_id": job_id, "status": "failed", "message": str(exc)}

    def extract_document(
        self,
        document_id: int,
        job_id: int,
        *,
        finalize_job: bool = True,
        progress_start: int = 0,
        progress_end: int = 100,
    ) -> dict:
        """仅对单个文档的段落 Block 执行 EIU 抽取（单文档隔离，不清全库）。

        仅删除该文档自身的旧 EIU，不影响其他文档已抽取的知识点。
        """
        try:
            return self._run(
                job_id,
                document_id=document_id,
                finalize_job=finalize_job,
                progress_start=progress_start,
                progress_end=progress_end,
            )
        except Exception as exc:  # noqa: BLE001
            self.database.update_job(
                job_id, status="failed", phase="eiu_extract", message=f"EIU 抽取失败: {exc}"
            )
            return {"job_id": job_id, "status": "failed", "message": str(exc)}

    def _run(
        self,
        job_id: int,
        document_id: int | None = None,
        *,
        finalize_job: bool = True,
        progress_start: int = 0,
        progress_end: int = 100,
    ) -> dict:
        # EIU 重抽会先删除旧数据；并发执行会互相覆盖，必须串行化。
        with self._run_lock:
            return self._run_locked(
                job_id,
                document_id=document_id,
                finalize_job=finalize_job,
                progress_start=progress_start,
                progress_end=progress_end,
            )

    def _run_locked(
        self,
        job_id: int,
        document_id: int | None = None,
        *,
        finalize_job: bool = True,
        progress_start: int = 0,
        progress_end: int = 100,
    ) -> dict:
        self._article_review_cache.clear()
        documents = self.database.list_documents()
        if document_id is not None:
            documents = [d for d in documents if d["document_id"] == document_id]
        document_blocks: list[list[dict]] = []
        for document in documents:
            document_blocks.append(self.database.get_document_blocks(document["document_id"]))

        all_blocks = [block for blocks in document_blocks for block in blocks]
        substantive = [block for block in all_blocks if block["block_type"] != "title"]
        total = len(substantive)
        if total == 0:
            if finalize_job:
                self.database.update_job(
                    job_id, status="completed", phase="done", progress=progress_end,
                    message="无可处理的段落", finished=True,
                )
            else:
                self.database.update_job(job_id, progress=progress_end)
            return {"job_id": job_id, "status": "completed", "message": "无可处理的段落", "count": 0}

        self.database.update_job(
            job_id, status="running", phase="eiu_extract", progress=progress_start,
            message=f"开始 EIU 抽取，共 {total} 个段落 Block",
        )
        # 单文档模式：仅清空该文档旧 EIU；全库模式：清空全部旧 EIU
        if document_id is not None:
            self.database.delete_eius_by_document(document_id=document_id)
        else:
            self.database.delete_eius_all()

        document_map = {document["document_id"]: document for document in documents}
        neighbors = self._build_neighbors(document_blocks)
        quality_evaluators = {
            document["document_id"]: EiuQualityEvaluator(blocks)
            for document, blocks in zip(documents, document_blocks)
        }
        inserted = 0
        excluded = 0
        _sem_vecs: list[tuple[str, list[float]]] = []  # 已插入 EIU 的 (归一化statement, 向量)
        # P1：EIU 向量 FAISS 索引，语义去重用（与 _sem_vecs 精确层互补）
        _faiss_idx = EiuFaissIndex()
        for index, block in enumerate(substantive, start=1):
            try:
                items = self._extract_block(block, document_map[block["document_id"]], neighbors[block["block_id"]])
            except LLMError as exc:
                items = []
                block_error = f"抽取失败: {str(exc)[:60]}"
            else:
                block_error = None
            # 语义去重：精确层（归一化 key）+ 语义层（FAISS 检索），同义者标记排除
            items = _dedup_semantic(items, _sem_vecs, _faiss_idx)
            evaluator = quality_evaluators[block["document_id"]]
            items = [evaluator.annotate(item, block) for item in items]
            if items:
                # P0：EIU 为核心实体，抽取时写入 statement 向量，落库供复用/跨块检索
                for it in items:
                    if it.get("is_questionable"):
                        stmt = (it.get("statement") or "").strip()
                        if stmt:
                            it["embedding_vector"] = _encode_one(stmt)
                inserted += len(self.database.save_eius(items=items))
                # 记录已插入可出题 EIU 的归一化 statement 向量，供后续块比对（精确层）
                for it in items:
                    if it.get("is_questionable"):
                        stmt = (it.get("statement") or "").strip()
                        if stmt:
                            _sem_vecs.append((_norm(stmt), _encode_one(stmt)))
                # 增量加入 FAISS 索引（语义层）
                _faiss_idx.add_items([it for it in items if it.get("embedding_vector")])
            else:
                exclusion = evaluator.annotate(
                    exclusion_item(block, block_error or "段落无实质内容，未抽取到 EIU"),
                    block,
                )
                self.database.save_eius(
                    items=[exclusion],
                )
                excluded += 1
            progress = progress_start + int(index / total * (progress_end - progress_start))
            self.database.update_job(job_id, progress=progress)

        if finalize_job:
            self.database.update_job(
                job_id, status="completed", phase="done", progress=progress_end,
                message=f"EIU 抽取完成，共 {inserted} 条（排除 {excluded} 个段落）", finished=True,
            )
        else:
            self.database.update_job(job_id, progress=progress_end)
        return {
            "job_id": job_id,
            "status": "completed",
            "message": f"EIU 抽取完成，共 {inserted} 条",
            "count": inserted,
        }
