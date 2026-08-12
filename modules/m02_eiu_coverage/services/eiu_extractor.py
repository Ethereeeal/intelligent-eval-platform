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
from pathlib import Path

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


def _default_constraints() -> dict:
    return {"主体": None, "条件": None, "范围": None, "期间": None, "币种": None, "单位": None}


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
    return constraints


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
                "statement": statement[: _STATEMENT_MAX],
                "eiu_type": eiu_type,
                "content_priority": priority,
                "constraints": _constraints_for(sentence),
                "is_questionable": True,
                "exclusion_reason": None,
                "extraction_model": "offline-rule-based",
                "extraction_confidence": 0.5,
            }
        )
    return results


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
        "statement": statement[:_STATEMENT_MAX],
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


def _dedup_semantic(items: list[dict], seen: list[tuple[str, list[float]]]) -> list[dict]:
    """对一批抽出的 EIU 做语义去重（跨 Block 同义合并）。

    - 精确层：归一化 statement 与已插入者完全一致 → 重复；
    - 语义层：BGE 余弦相似度 ≥ SEMANTIC_DEDUP_THRESHOLD → 同义重复；
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
        for seen_k, seen_vec in seen:
            if seen_k == k:
                dup = True
                break
            if seen_vec is not None:
                vec = _encode_one(stmt)
                if vec is not None:
                    sim = sum(a * b for a, b in zip(vec, seen_vec))
                    if sim >= SEMANTIC_DEDUP_THRESHOLD:
                        dup = True
                        break
        if dup:
            it = dict(it)
            it["is_questionable"] = False
            it["exclusion_reason"] = "与已抽取知识点语义重复（同义去重）"
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
class EiuExtractorService:
    def __init__(self) -> None:
        self.database = DatabaseService()
        self.llm = LLMClient()
        self.system_prompt = self._load_prompt()

    @staticmethod
    def _load_prompt() -> str:
        try:
            return _PROMPT_PATH.read_text(encoding="utf-8")
        except OSError:
            return "你是一位精通银行授信政策和金融监管文件的专家。"

    def extract_corpus(self, job_id: int) -> dict:
        """对全部文档的段落 Block 执行 EIU 抽取（后台线程调用）。

        全量重算：先清空全部旧 EIU，再逐 Block 抽取写入。
        """
        try:
            return self._run(job_id)
        except Exception as exc:  # noqa: BLE001 — 记录失败并置 job 状态
            self.database.update_job(
                job_id, status="failed", phase="extracting", message=f"EIU 抽取失败: {exc}"
            )
            return {"job_id": job_id, "status": "failed", "message": str(exc)}

    def extract_document(self, document_id: int, job_id: int) -> dict:
        """仅对单个文档的段落 Block 执行 EIU 抽取（单文档隔离，不清全库）。

        仅删除该文档自身的旧 EIU，不影响其他文档已抽取的知识点。
        """
        try:
            return self._run(job_id, document_id=document_id)
        except Exception as exc:  # noqa: BLE001
            self.database.update_job(
                job_id, status="failed", phase="extracting", message=f"EIU 抽取失败: {exc}"
            )
            return {"job_id": job_id, "status": "failed", "message": str(exc)}

    def _run(self, job_id: int, document_id: int | None = None) -> dict:
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
            self.database.update_job(
                job_id, status="completed", phase="done", progress=100,
                message="无可处理的段落", finished=True,
            )
            return {"job_id": job_id, "status": "completed", "message": "无可处理的段落", "count": 0}

        self.database.update_job(
            job_id, status="running", phase="extracting", progress=0,
            message=f"开始 EIU 抽取，共 {total} 个段落 Block",
        )
        # 单文档模式：仅清空该文档旧 EIU；全库模式：清空全部旧 EIU
        if document_id is not None:
            self.database.delete_eius_by_document(document_id=document_id)
        else:
            self.database.delete_eius_all()

        document_map = {document["document_id"]: document for document in documents}
        neighbors = self._build_neighbors(document_blocks)

        inserted = 0
        excluded = 0
        _sem_vecs: list[tuple[str, list[float]]] = []  # 已插入 EIU 的 (归一化statement, 向量)
        for index, block in enumerate(substantive, start=1):
            try:
                items = self._extract_block(block, document_map[block["document_id"]], neighbors[block["block_id"]])
            except LLMError as exc:
                items = []
                block_error = f"抽取失败: {str(exc)[:60]}"
            else:
                block_error = None
            # 语义去重：与本次已插入的知识点比对，同义（措辞不同但同义）者标记排除
            items = _dedup_semantic(items, _sem_vecs)
            if items:
                inserted += len(self.database.save_eius(items=items))
                # 记录已插入可出题 EIU 的归一化 statement 向量，供后续块比对
                for it in items:
                    if it.get("is_questionable"):
                        stmt = (it.get("statement") or "").strip()
                        if stmt:
                            _sem_vecs.append((_norm(stmt), _encode_one(stmt)))
            else:
                self.database.save_eius(
                    items=[exclusion_item(block, block_error or "段落无实质内容，未抽取到 EIU")],
                )
                excluded += 1
            self.database.update_job(job_id, progress=int(index / total * 100))

        self.database.update_job(
            job_id, status="completed", phase="done", progress=100,
            message=f"EIU 抽取完成，共 {inserted} 条（排除 {excluded} 个段落）", finished=True,
        )
        return {
            "job_id": job_id,
            "status": "completed",
            "message": f"EIU 抽取完成，共 {inserted} 条",
            "count": inserted,
        }

    @staticmethod
    def _build_neighbors(document_blocks: list[list[dict]]) -> dict[int, dict[str, str]]:
        """block_id → 前 1 / 后 1 个 Block 文本（上下文，SPEC §5.4 第 2 步）。"""
        neighbors: dict[int, dict[str, str]] = {}
        for blocks in document_blocks:
            for index, block in enumerate(blocks):
                neighbors[block["block_id"]] = {
                    "prev": blocks[index - 1]["block_text"] if index > 0 else "",
                    "next": blocks[index + 1]["block_text"] if index + 1 < len(blocks) else "",
                }
        return neighbors

    def _extract_block(self, block: dict, document: dict, context: dict[str, str]) -> list[dict]:
        """单 Block 抽取（混合策略：规则写死 + LLM 仅处理复杂句）。

        写死项（不再让 LLM 自由裁量）：
          - #2 EIU 类型判定：由 _classify 规则映射
          - #3 优先级 P0/P1/P2：由 _classify 类型→优先级映射
          - #5 constraints：由 _constraints_for 正则预抽
          - #4 粗筛：is_skippable 前置拦截，减少送 LLM 的 Block 数
        保留 LLM 项：
          - #1 拆分：规则先拆，规则无法归类的复杂句才交 LLM 进一步拆分
          - #4 语义排除（证据残缺不可出题）：仅对规则无法归类的 Block 用 LLM 判定

        策略：先跑确定性规则抽取。若规则已能归类（绝大多数监管条款），直接采用、
        跳过 LLM；仅当规则无法归类（返回空）时，才调用 LLM 处理复杂句，且对 LLM
        产出的每条 EIU 仍用规则重算 type/priority/constraints（保证写死）。

        表格类文件（excel/csv）不做特殊化：与普通文档走同一套抽取流程，
        一行内可抽 0..n 条 EIU（规则逐句分类先抽，规则无法归类时交 LLM）。

        唯一例外：表头含「问题/question」列时，以问题列为抽取输入，
        避免「答案」列混入 EIU statement（否则生成题目会泄露标准答案）。
        """
        # excel/csv 行若带「问题」列，用问题列文本作为 EIU 抽取输入（答案列不混入）
        meta = block.get("metadata_json") or {}
        if block.get("block_type") == "excel_row" and (meta.get("question") or "").strip():
            text = str(meta.get("question")).strip()
        else:
            text = block["block_text"]
        if is_skippable(text):                       # #4 粗筛写死，前置拦截
            return []

        # 1) 规则先抽（#2/#3/#5 写死在此完成）
        rule_items = deterministic_extract(text)
        for item in rule_items:
            item["block_id"] = block["block_id"]
            item["extraction_model"] = "hybrid-rule"
            item["extraction_confidence"] = 0.9

        if rule_items:
            # 规则能归类 → 直接采用，省掉本次 LLM 调用
            return rule_items

        # 2) 规则无法归类（复杂/语义句）→ 交给 LLM 做 #1 拆分与 #4 语义排除
        if self.llm.use_offline:
            return []  # 离线且规则无法归类，保守跳过，不杜撰

        try:
            user_prompt = self._build_user_prompt(block, document, context)
            raw_items = self.llm.extract_json(self.system_prompt, user_prompt)
        except LLMError:
            return []

        items: list[dict] = []
        seen: set[str] = set()
        for item in raw_items:
            statement = _clean_statement(str(item.get("statement", "")))
            if not statement or statement in seen:
                continue
            seen.add(statement)
            # #2/#3/#5 写死：用规则对 LLM 拆分出的语句重新归类，覆盖 LLM 自由裁量
            classification = _classify(statement)
            if classification is None:
                # 连规则都无法归类 → 视为 LLM 过度拆分，跳过该条（不杜撰类型）
                continue
            eiu_type, priority = classification
            normalized = {
                "statement": statement[:_STATEMENT_MAX],
                "eiu_type": eiu_type,
                "content_priority": priority,
                "constraints": _constraints_for(statement),
                "evidence_blocks": [block["block_id"]],
                "is_questionable": bool(item.get("is_questionable", True)),
                "exclusion_reason": (
                    None if item.get("is_questionable", True)
                    else str(item.get("exclusion_reason") or "语义不可出题")[:128]
                ),
                "extraction_model": "hybrid-llm",
                "extraction_confidence": 0.7,
            }
            items.append(normalized)
        return items

    @staticmethod
    def _build_user_prompt(block: dict, document: dict, context: dict[str, str]) -> str:
        # SPEC §5.3 User Prompt 模板
        return (
            "## 文档信息\n"
            f"- 文档名: {document['file_name']}\n"
            f"- 章节路径: {block['section_path']}\n"
            "\n"
            "## 上文（前一个 Block）\n"
            f"{context['prev'] or '（无）'}\n"
            "\n"
            "## 当前段落\n"
            f"{block['block_text']}\n"
            "\n"
            "## 下文（后一个 Block）\n"
            f"{context['next'] or '（无）'}\n"
            "\n"
            "请抽取当前段落中的 EIU。如果段落无实质内容，返回空数组 []。"
        )
