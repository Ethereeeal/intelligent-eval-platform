from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    or_,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from modules.shared.core.config import settings
from modules.shared.core.logging_config import get_logger

logger = get_logger(__name__)

# 10 种 EIU 类型（M02 SPEC 4.2）
EIU_TYPES = {
    "definition",
    "rule",
    "threshold",
    "date",
    "formula",
    "process",
    "exception",
    "prohibition",
    "metric",
    "change",
}

# 优先级 → 权重（M02 SPEC 4.3）
PRIORITY_WEIGHT = {"P0": 5, "P1": 3, "P2": 1}

# 编号前缀（如 "1." "（二）" "3.2"），用于 statement 归一化
_STATEMENT_NUM_PREFIX = re.compile(r"^\s*(?:\(?[0-9０-９]+\)?[\.\、]\s*)+")


def normalize_statement(text: str) -> str:
    """将 EIU statement 归一化为复用匹配键。

    去除编号前缀、结尾标点、空白，并统一为小写，使不同 corpus 中
    语义相同的陈述可以精确匹配（方案 B 跨库复用）。
    """
    if not text:
        return ""
    text = _STATEMENT_NUM_PREFIX.sub("", text.strip()).strip()
    text = re.sub(r"[。；;，,、\s]+$", "", text).strip()
    return text.lower()


def normalize_question(text: str) -> str:
    """归一化问句为查重 key（精确查重）。

    只去「不影响同一问题判定的」噪声，保留实质内容：
      - 统一全半角（中文全角 ，。？ 与半角 ,.? 视为同一）
      - 去掉所有空白（空格/换行）
      - 去掉尾部标点（？。！？;；等）
      - 统一小写
    不归一数字/同义词——保证只抓"一模一样（去除格式差异后相同）"的问题，
    不误伤相似但不同的问题。
    """
    if not text:
        return ""
    # 去所有空白（空格/换行/全角空格）
    text = re.sub(r"\s+", "", text)
    # 去所有中英文标点（中文问句中逗号/句号/问号等不改变实质语义）；
    # 保留 % 与 ％（数值的一部分，如 70% vs 70 不应视为同一）
    text = re.sub(r"[，。？、；：,\.\?!;:\"'“”‘’（）()【】\[\]·…—\-_/\\~`@#$^&*+=<>|]", "", text)
    text = text.replace("％", "%")  # 全角百分号统一为半角，仍是数值一部分
    return text.lower()


class Base(DeclarativeBase):
    pass


class DocumentRow(Base):
    __tablename__ = "document"

    document_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # 文件哈希全局唯一：同一文件全库不允许重复上传
    file_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    minio_path: Mapped[str] = mapped_column(String(512), nullable=False)
    upload_user: Mapped[str | None] = mapped_column(String(128), nullable=True)
    document_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    authority_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # 目录结构：相对根路径（如「合同/2024」），根目录为空；用于前端目录树重建
    folder_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # 业务用途：basic=基础问题输入文档，gen=仅泛化输入文档
    purpose: Mapped[str | None] = mapped_column(String(16), nullable=True)
    parse_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="uploaded")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("file_hash", name="uq_file_hash"),
    )


class FolderRow(Base):
    """文档库目录：用户自建文件夹，层级由 parent_id 自引用表达。

    owner 记录归属用户（当前无登录态，前端统一传 web）；后续接入真实账号
    体系后可按 owner 隔离各自的目录树。文档与文件夹通过 document.folder_path
    （相对「文档库」根的子路径）冗余关联。
    """

    __tablename__ = "folder"

    folder_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # 父文件夹 id；NULL = 直接挂在「文档库」根下
    parent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    owner: Mapped[str] = mapped_column(String(128), nullable=False, default="web")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuditLogRow(Base):
    """审计日志：删除 / 覆盖等破坏性操作留痕（BRD 12.3 / production-readiness P0#2）。"""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    actor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BlockRow(Base):
    __tablename__ = "document_block"

    block_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_block_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    section_path: Mapped[str] = mapped_column(String(512), nullable=False)
    page_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    block_type: Mapped[str] = mapped_column(String(64), nullable=False, default="paragraph")
    block_text: Mapped[str] = mapped_column(Text, nullable=False)
    start_offset: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    end_offset: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    embedding_vector: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class EiuRow(Base):
    """EIU — 可评测信息单元（M02 产出，绑定源 Block）。

    review_status: candidate / quality_verified / blocked
    blocked = 被 DELETE 软删除（不计入覆盖率分母）。
    """

    __tablename__ = "eiu"

    eiu_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    block_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    document_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    eiu_type: Mapped[str] = mapped_column(String(32), nullable=False)
    content_priority: Mapped[str] = mapped_column(String(4), nullable=False)
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    constraints_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    evidence_blocks: Mapped[list | None] = mapped_column(JSON, nullable=True)
    is_questionable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    exclusion_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    extraction_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    extraction_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="candidate")
    # EIU 级向量（P0：EIU 为核心实体；用于语义去重/复用/未来跨块检索）
    embedding_vector: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DocUpdateJobRow(Base):
    __tablename__ = "doc_update_job"

    job_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(Integer, nullable=False)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    phase: Mapped[str | None] = mapped_column(String(64), nullable=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class TaskJobRow(Base):
    __tablename__ = "task_job"

    job_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ChatSessionRow(Base):
    __tablename__ = "chat_session"

    session_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    title: Mapped[str] = mapped_column(String(255), default="新对话")
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ChatMessageRow(Base):
    __tablename__ = "chat_message"

    message_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    message_type: Mapped[str] = mapped_column(String(32), default="text")
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    intent_params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ----------------------------------------------------------------------
# m05 — 数据集生命周期：版本与样本
# ----------------------------------------------------------------------
class DatasetVersionRow(Base):
    __tablename__ = "dataset_version"

    version_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_number: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    case_count: Mapped[int] = mapped_column(Integer, default=0)
    coverage_report_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    split_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    snapshot_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class EvalCaseRow(Base):
    __tablename__ = "eval_case"

    case_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    case_uid: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    intent_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scope: Mapped[str | None] = mapped_column(String(64), nullable=True)
    difficulty: Mapped[str | None] = mapped_column(String(32), nullable=True)
    gold_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    must_have_points: Mapped[list | None] = mapped_column(JSON, nullable=True)
    acceptable_answers: Mapped[list | None] = mapped_column(JSON, nullable=True)
    evidence: Mapped[list | None] = mapped_column(JSON, nullable=True)
    eiu_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    content_priority: Mapped[str | None] = mapped_column(String(32), nullable=True)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="candidate")
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="native")
    retired: Mapped[bool] = mapped_column(default=False)


# ----------------------------------------------------------------------
# m02 — 覆盖率报告快照（供 m05 冻结版本外键引用）
# ----------------------------------------------------------------------
class CoverageReportRow(Base):
    __tablename__ = "coverage_report"

    report_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    total_eiu: Mapped[int] = mapped_column(Integer, default=0)
    questionable_eiu: Mapped[int] = mapped_column(Integer, default=0)
    excluded_eiu: Mapped[int] = mapped_column(Integer, default=0)
    by_priority: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    by_type: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    by_document: Mapped[list | None] = mapped_column(JSON, nullable=True)
    by_section: Mapped[list | None] = mapped_column(JSON, nullable=True)
    weighted_coverage: Mapped[float] = mapped_column(default=0.0)
    p0_coverage_pct: Mapped[float] = mapped_column(default=0.0)
    block_reconciliation: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    alerts: Mapped[list | None] = mapped_column(JSON, nullable=True)
    snapshot_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@dataclass
class DatabaseResult:
    document_id: int
    block_ids: list[int]


class DatabaseService:
    def create_all(self) -> None:
        Base.metadata.create_all(bind=engine)
        # SQLite 不支持 create_all 自动加列：为已存在的表补 statement_norm 列
        from sqlalchemy import inspect

        inspector = inspect(engine)
        if "generated_case" in inspector.get_table_names():
            cols = {c["name"] for c in inspector.get_columns("generated_case")}
            if "statement_norm" not in cols:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            "ALTER TABLE generated_case ADD COLUMN statement_norm VARCHAR(512)"
                        )
                    )
        # document.file_hash：全库唯一（同一文件不允许重复上传）
        if "document" in inspector.get_table_names():
            cols = {c["name"] for c in inspector.get_columns("document")}
            index_names = {ix["name"] for ix in inspector.get_indexes("document")}
            # 先删依赖 corpus_id 的复合唯一索引（否则 DROP COLUMN 会失败）；再删列
            if "uq_corpus_file_hash" in index_names:
                try:
                    with engine.begin() as conn:
                        conn.execute(text("DROP INDEX IF EXISTS uq_corpus_file_hash"))
                except Exception:
                    pass
            if "corpus_id" in cols:
                try:
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE document DROP COLUMN corpus_id"))
                except Exception:
                    pass
        # document.folder_path / purpose：目录结构与业务用途（基础/泛化）
        if "document" in inspector.get_table_names():
            cols = {c["name"] for c in inspector.get_columns("document")}
            with engine.begin() as conn:
                if "folder_path" not in cols:
                    conn.execute(text("ALTER TABLE document ADD COLUMN folder_path VARCHAR(512) NULL"))
                if "purpose" not in cols:
                    conn.execute(text("ALTER TABLE document ADD COLUMN purpose VARCHAR(16) NULL"))
        # generated_case.folder_path / purpose：问答对库目录结构（与 document 同构）
        if "generated_case" in inspector.get_table_names():
            gcols = {c["name"] for c in inspector.get_columns("generated_case")}
            with engine.begin() as conn:
                if "folder_path" not in gcols:
                    conn.execute(text("ALTER TABLE generated_case ADD COLUMN folder_path VARCHAR(512) NULL"))
                if "purpose" not in gcols:
                    conn.execute(text("ALTER TABLE generated_case ADD COLUMN purpose VARCHAR(16) NULL"))
        # eiu.document_id：冗余存储归属文件，使 EIU 可按文件目录组织（去掉 corpus 维度）
        if "eiu" in inspector.get_table_names():
            eiu_cols = {c["name"] for c in inspector.get_columns("eiu")}
            with engine.begin() as conn:
                if "document_id" not in eiu_cols:
                    conn.execute(text("ALTER TABLE eiu ADD COLUMN document_id INTEGER NULL"))
                # eiu.embedding_vector：EIU 级向量（P0 改造，EIU 为核心实体，支持去重/复用/跨块检索）
                if "embedding_vector" not in eiu_cols:
                    conn.execute(text("ALTER TABLE eiu ADD COLUMN embedding_vector JSON NULL"))
                # 回填历史 EIU：经 block_id -> document_id 反查（仅更新尚未回填的）
                # 使用跨数据库兼容的子查询写法（MySQL JOIN UPDATE 在 SQLite 下不支持）
                conn.execute(
                    text(
                        "UPDATE eiu SET document_id = ("
                        "SELECT b.document_id FROM document_block b "
                        "WHERE b.block_id = eiu.block_id) "
                        "WHERE document_id IS NULL"
                    )
                )
                if "corpus_id" in eiu_cols:
                    try:
                        conn.execute(text("ALTER TABLE eiu DROP COLUMN corpus_id"))
                    except Exception:
                        pass
        # 删除 corpus 表及其在各表中的 corpus_id 列（彻底去 corpus 概念）
        if "corpus" in inspector.get_table_names():
            try:
                with engine.begin() as conn:
                    conn.execute(text("DROP TABLE corpus"))
            except Exception:
                pass
        for tbl in ("generated_case", "doc_update_job", "chat_session", "dataset_version", "coverage_report"):
            if tbl in inspector.get_table_names():
                tcols = {c["name"] for c in inspector.get_columns(tbl)}
                if "corpus_id" in tcols:
                    try:
                        with engine.begin() as conn:
                            conn.execute(text(f"ALTER TABLE {tbl} DROP COLUMN corpus_id"))
                    except Exception:
                        pass

    def save_document(
        self,
        *,
        file_name: str,
        file_type: str,
        file_hash: str,
        minio_path: str,
        file_size: int | None = None,
        upload_user: str | None = None,
        document_version: str | None = None,
        parse_status: str | None = None,
        folder_path: str | None = None,
        purpose: str | None = None,
    ) -> int:
        with SessionLocal() as session:
            row = DocumentRow(
                file_name=file_name,
                file_type=file_type,
                file_size=file_size,
                file_hash=file_hash,
                minio_path=minio_path,
                upload_user=upload_user,
                document_version=document_version,
                parse_status=parse_status,
                folder_path=folder_path,
                purpose=purpose,
                status="uploaded",
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row.document_id

    def find_by_hash(self, file_hash: str) -> int | None:
        """Return existing document_id for the given hash (全库唯一，同一文件不允许重复上传)."""
        with SessionLocal() as session:
            row = session.query(DocumentRow).filter(DocumentRow.file_hash == file_hash).first()
            return row.document_id if row else None

    def find_document_by_name_in_folder(self, file_name: str, folder_path: str | None) -> dict | None:
        """按「文件名 + 目标文件夹」查找文档（上传预检同名覆盖判定用）。

        根目录兼容两种历史写法：folder_path 为 None 或空串均视为文档库根。
        """
        fp = str(folder_path or "").strip("/")
        with SessionLocal() as session:
            condition = (
                or_(DocumentRow.folder_path.is_(None), DocumentRow.folder_path == "")
                if fp == ""
                else DocumentRow.folder_path == fp
            )
            row = (
                session.query(DocumentRow)
                .filter(DocumentRow.file_name == file_name, condition)
                .first()
            )
            if row is None:
                return None
            return {
                "document_id": row.document_id,
                "file_name": row.file_name,
                "file_size": row.file_size,
                "file_hash": row.file_hash,
                "folder_path": row.folder_path,
                "upload_time": row.created_at.isoformat() if row.created_at else None,
            }

    def find_documents_by_name(self, file_name: str) -> list[dict]:
        """全库按文件名查找文档（上传预检弱提示：其他位置同名）。"""
        with SessionLocal() as session:
            rows = (
                session.query(DocumentRow)
                .filter(DocumentRow.file_name == file_name)
                .order_by(DocumentRow.document_id.desc())
                .all()
            )
            return [
                {
                    "document_id": row.document_id,
                    "file_name": row.file_name,
                    "folder_path": row.folder_path,
                    "upload_time": row.created_at.isoformat() if row.created_at else None,
                }
                for row in rows
            ]

    def save_blocks(self, *, document_id: int, blocks: list[dict]) -> list[int]:
        rows: list[BlockRow] = []
        with SessionLocal() as session:
            for block in blocks:
                row = BlockRow(
                    document_id=document_id,
                    parent_block_id=block.get("parent_block_id"),
                    section_path=block["section_path"],
                    page_no=block.get("page_no"),
                    block_type=block.get("block_type", "paragraph"),
                    block_text=block["block_text"],
                    start_offset=block.get("start_offset"),
                    end_offset=block.get("end_offset"),
                    metadata_json=block.get("metadata_json"),
                    embedding_vector=block.get("embedding_vector"),
                )
                session.add(row)
                rows.append(row)
            session.flush()
            block_ids = [row.block_id for row in rows]
            # parent_index 指向结果列表中的位置，落库后解析为真实的 block_id
            for index, block in enumerate(blocks):
                parent_index = block.get("parent_index")
                if parent_index is not None and 0 <= parent_index < len(block_ids):
                    rows[index].parent_block_id = block_ids[parent_index]
            session.commit()
        return block_ids

    def list_blocks(self) -> list[dict]:
        with SessionLocal() as session:
            query = session.query(BlockRow, DocumentRow).join(DocumentRow, BlockRow.document_id == DocumentRow.document_id)
            rows = query.all()
            return [
                {
                    "block_id": block.block_id,
                    "document_id": block.document_id,
                    "parent_block_id": block.parent_block_id,
                    "section_path": block.section_path,
                    "page_no": block.page_no,
                    "block_type": block.block_type,
                    "block_text": block.block_text,
                    "start_offset": block.start_offset,
                    "end_offset": block.end_offset,
                    "metadata_json": block.metadata_json,
                    "embedding_vector": block.embedding_vector,
                }
                for block, _document in rows
            ]

    # ------------------------------------------------------------------
    # document
    # ------------------------------------------------------------------
    def get_document(self, document_id: int) -> dict | None:
        with SessionLocal() as session:
            row = session.get(DocumentRow, document_id)
            if not row:
                return None
            return {
                "document_id": row.document_id,
                "file_name": row.file_name,
                "file_type": row.file_type,
                "file_size": row.file_size,
                "file_hash": row.file_hash,
                "minio_path": row.minio_path,
                "upload_user": row.upload_user,
                "document_version": row.document_version,
                "authority_level": row.authority_level,
                "parse_status": row.parse_status,
                "parse_error": row.parse_error,
                "status": row.status,
                "folder_path": row.folder_path,
                "purpose": row.purpose,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }

    def find_document_by_id(self, document_id: int) -> int | None:
        with SessionLocal() as session:
            row = session.get(DocumentRow, document_id)
            return row.document_id if row else None

    def list_documents(self) -> list[dict]:
        with SessionLocal() as session:
            query = session.query(DocumentRow)
            rows = query.order_by(DocumentRow.document_id.desc()).all()
            return [
                {
                    "document_id": row.document_id,
                    "file_name": row.file_name,
                    "file_type": row.file_type,
                    "file_size": row.file_size,
                    "parse_status": row.parse_status,
                    "status": row.status,
                    "folder_path": row.folder_path,
                    "purpose": row.purpose,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in rows
            ]

    def update_document(
        self,
        document_id: int,
        *,
        parse_status: str | None = None,
        parse_error: str | None = None,
        status: str | None = None,
        file_hash: str | None = None,
        minio_path: str | None = None,
        file_size: int | None = None,
        folder_path: str | None = None,
        purpose: str | None = None,
        file_name: str | None = None,
    ) -> None:
        with SessionLocal() as session:
            row = session.get(DocumentRow, document_id)
            if not row:
                return
            if parse_status is not None:
                row.parse_status = parse_status
            if parse_error is not None:
                row.parse_error = parse_error
            if status is not None:
                row.status = status
            if file_hash is not None:
                row.file_hash = file_hash
            if minio_path is not None:
                row.minio_path = minio_path
            if file_size is not None:
                row.file_size = file_size
            if folder_path is not None:
                row.folder_path = folder_path
            if purpose is not None:
                row.purpose = purpose
            if file_name is not None:
                row.file_name = file_name
            session.commit()

    def delete_document_blocks(self, document_id: int) -> None:
        with SessionLocal() as session:
            session.query(BlockRow).filter(BlockRow.document_id == document_id).delete()
            session.commit()

    def delete_document(self, document_id: int) -> None:
        """物理删除文档及其全部附属数据（解析块 + 知识点 EIU + 问答对 + 质检结果 + 文档行）。

        删除文档 = 彻底弃用该文档：其知识点（EIU）与问答对库中由该文档生成的
        问答对（generated_case）一并物理删除，质检结果（quality_check_result）
        随问答对清理，避免残留孤儿数据。覆盖重算后清理旧文档用；
        m05 dataset_version 为独立版本快照表，不在此处删除。
        """
        existing = self.get_document(document_id)
        if existing is None:
            return
        # 1) 先删该文档的知识点（依赖 block_id）
        self.delete_eius_by_document(document_id=document_id)
        # 2) 再删解析块
        self.delete_document_blocks(document_id)
        # 3) 删该文档的问答对（generated_case）及其质检结果
        with SessionLocal() as session:
            case_ids = [
                r[0]
                for r in session.query(GeneratedCaseRow.case_id)
                .filter(GeneratedCaseRow.document_id == document_id)
                .all()
            ]
            if case_ids:
                session.query(QualityCheckRow).filter(
                    QualityCheckRow.case_id.in_(case_ids)
                ).delete(synchronize_session=False)
            session.query(GeneratedCaseRow).filter(
                GeneratedCaseRow.document_id == document_id
            ).delete(synchronize_session=False)
            session.commit()
        # 4) 最后删文档行
        with SessionLocal() as session:
            session.query(DocumentRow).filter(DocumentRow.document_id == document_id).delete()
            session.commit()

    # ------------------------------------------------------------------
    # folder — 文档库目录（用户自建文件夹，持久化；空文件夹刷新后仍保留）
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_path(path: str | None) -> str:
        return str(path or "").strip("/")

    def list_folders(self, owner: str | None = None) -> list[dict]:
        """返回文件夹扁平列表 [{folder_id, name, parent_id, owner}]。

        当前无真实登录体系，owner 仅作记录，不按 owner 过滤（避免历史 seed
        文档（upload_user=demo）与新用户文件夹树割裂）。
        """
        with SessionLocal() as session:
            query = session.query(FolderRow)
            if owner:
                query = query.filter(FolderRow.owner == owner)
            rows = query.order_by(FolderRow.folder_id.asc()).all()
            return [
                {
                    "folder_id": row.folder_id,
                    "name": row.name,
                    "parent_id": row.parent_id,
                    "owner": row.owner,
                }
                for row in rows
            ]

    @staticmethod
    def _folder_by_path(session: Session, path: str) -> FolderRow | None:
        """按「相对文档库根」的路径（如 A/B）逐级查找文件夹；找不到返回 None。"""
        parent_id: int | None = None
        row: FolderRow | None = None
        for name in path.split("/"):
            if not name:
                continue
            row = (
                session.query(FolderRow)
                .filter(FolderRow.name == name, FolderRow.parent_id == parent_id)
                .first()
            )
            if row is None:
                return None
            parent_id = row.folder_id
        return row

    def _ensure_in_session(self, session: Session, owner: str, path: str) -> int | None:
        """在已有 session 中确保路径上的文件夹都存在，返回最深 folder_id（根返回 None）。"""
        fp = self._normalize_path(path)
        if not fp:
            return None
        parent_id: int | None = None
        for name in fp.split("/"):
            if not name:
                continue
            row = (
                session.query(FolderRow)
                .filter(FolderRow.name == name, FolderRow.parent_id == parent_id)
                .first()
            )
            if row is None:
                row = FolderRow(name=name, parent_id=parent_id, owner=owner)
                session.add(row)
                session.flush()
            parent_id = row.folder_id
        return parent_id

    def ensure_folder_path(self, owner: str, path: str | None) -> int | None:
        """确保 folder_path（相对文档库根，如 A/B）路径上的文件夹均有记录。

        上传/移动文档时调用，保证目标目录持久化；返回最深文件夹 id（根返回 None）。
        """
        fp = self._normalize_path(path)
        if not fp:
            return None
        with SessionLocal() as session:
            fid = self._ensure_in_session(session, owner, fp)
            session.commit()
            return fid

    def create_folder(self, *, owner: str, name: str, parent_path: str | None = None) -> dict:
        """在 parent_path（相对文档库根，空=根下）创建子文件夹，同父下禁止重名。"""
        name = str(name or "").strip()
        if not name or "/" in name:
            raise ValueError("文件夹名不能为空且不能包含 /")
        parent_id = self.ensure_folder_path(owner, parent_path) if parent_path else None
        with SessionLocal() as session:
            dup = (
                session.query(FolderRow)
                .filter(FolderRow.name == name, FolderRow.parent_id == parent_id)
                .first()
            )
            if dup is not None:
                raise ValueError(f"目标目录已存在同名文件夹：{name}")
            row = FolderRow(name=name, parent_id=parent_id, owner=owner)
            session.add(row)
            session.commit()
            session.refresh(row)
            return {
                "folder_id": row.folder_id,
                "name": row.name,
                "parent_id": row.parent_id,
                "owner": row.owner,
            }

    def rename_folder(self, *, owner: str, from_path: str, to_path: str) -> dict:
        """移动/重命名文件夹：from_path（旧相对路径）→ to_path（新完整路径）。

        文件夹层级由 parent_id 表达，子孙文件夹路径自动随链变化，无需逐行更新；
        但 document.folder_path 是冗余路径字符串，需按前缀重写。
        """
        fp = self._normalize_path(from_path)
        tp = self._normalize_path(to_path)
        if not fp or not tp:
            raise ValueError("文件夹路径不能为空")
        with SessionLocal() as session:
            row = self._folder_by_path(session, fp)
            if row is None:
                raise ValueError(f"文件夹不存在：{fp}")
            to_parts = tp.split("/")
            new_name = to_parts[-1]
            new_parent_path = "/".join(to_parts[:-1])
            new_parent_id = self._ensure_in_session(session, owner, new_parent_path)
            # 自身不能移动到自身/子孙内部（避免成环）：新父路径不得以 fp 为前缀
            if new_parent_path == fp or new_parent_path.startswith(fp + "/"):
                raise ValueError("不能把文件夹移动到自身或其子文件夹内")
            dup = (
                session.query(FolderRow)
                .filter(
                    FolderRow.name == new_name,
                    FolderRow.parent_id == new_parent_id,
                    FolderRow.folder_id != row.folder_id,
                )
                .first()
            )
            if dup is not None:
                raise ValueError(f"目标目录已存在同名文件夹：{new_name}")
            row.name = new_name
            row.parent_id = new_parent_id
            session.flush()
            # 重写该文件夹下文档的 folder_path 前缀（文档路径字符串随目录变更）
            for doc in session.query(DocumentRow).all():
                dfp = doc.folder_path or ""
                if dfp == fp:
                    doc.folder_path = tp
                elif dfp.startswith(fp + "/"):
                    doc.folder_path = tp + dfp[len(fp):]
            # 同构：问答对库（generated_case）folder_path 也随目录变更重写
            for gc in session.query(GeneratedCaseRow).all():
                gfp = gc.folder_path or ""
                if gfp == fp:
                    gc.folder_path = tp
                elif gfp.startswith(fp + "/"):
                    gc.folder_path = tp + gfp[len(fp):]
            session.commit()
            return {
                "folder_id": row.folder_id,
                "name": new_name,
                "parent_id": new_parent_id,
                "owner": row.owner,
            }

    def delete_folder(self, *, owner: str | None, path: str) -> dict:
        """删除文件夹（递归子孙）。

        - 文档（DocumentRow）：上移到父目录（仅调整 folder_path，不丢文档，
          文档的物理删除由 DELETE /api/documents/{id} 单独负责）。
        - 问答对（GeneratedCaseRow）：本文件夹及子孙目录下归属的问答对**一并物理删除**
          （与「删除文档会连带删除其问答对」的语义保持一致：文件夹在问答对库中是数据容器）。
        - 最后物理删除文件夹行本身。
        """
        fp = self._normalize_path(path)
        if not fp:
            raise ValueError("文件夹路径不能为空")
        parent_path = "/".join(fp.split("/")[:-1])
        with SessionLocal() as session:
            row = self._folder_by_path(session, fp)
            if row is None:
                raise ValueError(f"文件夹不存在：{fp}")
            # 递归收集该文件夹及其全部子孙 id
            ids = [row.folder_id]

            def collect(pid: int) -> None:
                for c in session.query(FolderRow).filter(FolderRow.parent_id == pid).all():
                    ids.append(c.folder_id)
                    collect(c.folder_id)

            collect(row.folder_id)
            # 文档上移到父目录：去掉被删文件夹前缀段（不丢文档）
            for doc in session.query(DocumentRow).all():
                dfp = doc.folder_path or ""
                if dfp == fp:
                    doc.folder_path = parent_path
                elif dfp.startswith(fp + "/"):
                    doc.folder_path = (
                        (parent_path + "/" + dfp[len(fp) + 1:]) if parent_path else dfp[len(fp) + 1:]
                    )
            # 问答对：本目录及子孙目录下归属的问答对一并物理删除
            deleted_cases = (
                session.query(GeneratedCaseRow)
                .filter(
                    (GeneratedCaseRow.folder_path == fp)
                    | (GeneratedCaseRow.folder_path.startswith(fp + "/", autoescape=True))
                )
                .delete(synchronize_session=False)
            )
            session.query(FolderRow).filter(FolderRow.folder_id.in_(ids)).delete(
                synchronize_session=False
            )
            session.commit()
            return {"deleted_folders": len(ids), "deleted_cases": deleted_cases}

    def get_document_blocks(self, document_id: int) -> list[dict]:
        with SessionLocal() as session:
            rows = (
                session.query(BlockRow)
                .filter(BlockRow.document_id == document_id)
                .order_by(BlockRow.block_id.asc())
                .all()
            )
            return [
                {
                    "block_id": row.block_id,
                    "document_id": row.document_id,
                    "parent_block_id": row.parent_block_id,
                    "section_path": row.section_path,
                    "page_no": row.page_no,
                    "block_type": row.block_type,
                    "block_text": row.block_text,
                    "start_offset": row.start_offset,
                    "end_offset": row.end_offset,
                    "metadata_json": row.metadata_json,
                }
                for row in rows
            ]

    # ------------------------------------------------------------------
    # doc_update_job
    # ------------------------------------------------------------------
    def save_job(self, *, document_id: int, job_type: str) -> int:
        with SessionLocal() as session:
            row = DocUpdateJobRow(
                document_id=document_id,
                job_type=job_type,
                status="pending",
                phase="queued",
                progress=0,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row.job_id

    def update_job(
        self,
        job_id: int,
        *,
        status: str | None = None,
        phase: str | None = None,
        progress: int | None = None,
        message: str | None = None,
        finished: bool = False,
    ) -> None:
        with SessionLocal() as session:
            row = session.get(DocUpdateJobRow, job_id)
            if not row:
                return
            if status is not None:
                row.status = status
            if phase is not None:
                row.phase = phase
            if progress is not None:
                row.progress = progress
            if message is not None:
                row.message = message
            if finished:
                row.finished_at = datetime.utcnow()
            session.commit()

    def get_job(self, job_id: int) -> dict | None:
        with SessionLocal() as session:
            row = session.get(DocUpdateJobRow, job_id)
            if not row:
                return None
            return {
                "job_id": row.job_id,
                "document_id": row.document_id,
                "job_type": row.job_type,
                "status": row.status,
                "phase": row.phase,
                "progress": row.progress,
                "message": row.message,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            }

    # ------------------------------------------------------------------
    # audit — 破坏性操作审计（BRD 12.3）
    # ------------------------------------------------------------------
    def save_audit(
        self,
        *,
        operation: str,
        target_type: str | None = None,
        target_id: str | None = None,
        actor: str | None = None,
        detail: dict | None = None,
    ) -> None:
        """写入一条审计记录（删除 / 覆盖等破坏性操作必须留痕）。"""
        with SessionLocal() as session:
            session.add(
                AuditLogRow(
                    operation=operation,
                    target_type=target_type,
                    target_id=target_id,
                    actor=actor,
                    detail=detail,
                )
            )
            session.commit()

    # ------------------------------------------------------------------
    # eiu（M02 — EIU 抽取与覆盖规划）
    # ------------------------------------------------------------------
    @staticmethod
    def _eiu_to_dict(eiu: EiuRow, block: BlockRow | None = None, document: DocumentRow | None = None) -> dict:
        return {
            "eiu_id": eiu.eiu_id,
            "block_id": eiu.block_id,
            "document_id": block.document_id if block else None,
            "document_name": document.file_name if document else None,
            "section_path": block.section_path if block else None,
            "statement": eiu.statement,
            "eiu_type": eiu.eiu_type,
            "content_priority": eiu.content_priority,
            "weight": eiu.weight,
            "constraints": eiu.constraints_json,
            "evidence_blocks": eiu.evidence_blocks,
            "is_questionable": bool(eiu.is_questionable),
            "exclusion_reason": eiu.exclusion_reason,
            "extraction_model": eiu.extraction_model,
            "extraction_confidence": eiu.extraction_confidence,
            "review_status": eiu.review_status,
            "embedding_vector": eiu.embedding_vector,
            "created_at": eiu.created_at.isoformat() if eiu.created_at else None,
        }

    def save_eius(self, *, items: list[dict]) -> list[int]:
        """批量写入 EIU。

        items 中每条必须含 block_id / statement / eiu_type / content_priority，
        其余字段可选。批内按 (block_id, statement) 去重（SPEC D6）。
        """
        if not items:
            return []
        with SessionLocal() as session:
            # 预查 block_id -> document_id 映射，写入冗余列便于按文件目录组织
            block_ids = [it["block_id"] for it in items if it.get("block_id") is not None]
            block_doc_map: dict[int, int] = {}
            if block_ids:
                mapping = (
                    session.query(BlockRow.block_id, BlockRow.document_id)
                    .filter(BlockRow.block_id.in_(block_ids))
                    .all()
                )
                block_doc_map = {bid: did for bid, did in mapping}
            seen: set[tuple[int, str]] = set()
            rows: list[EiuRow] = []
            for item in items:
                key = (item["block_id"], item["statement"])
                if key in seen:
                    continue
                seen.add(key)
                priority = item.get("content_priority", "P2")
                is_questionable = bool(item.get("is_questionable", True))
                exclusion_reason = str(item.get("exclusion_reason") or "").strip()
                if not is_questionable and not exclusion_reason:
                    raise ValueError("不可出题 EIU 必须提供 exclusion_reason")
                row = EiuRow(
                    block_id=item["block_id"],
                    document_id=block_doc_map.get(item["block_id"]),
                    statement=item["statement"],
                    eiu_type=item.get("eiu_type", "rule"),
                    content_priority=priority,
                    weight=PRIORITY_WEIGHT.get(priority, 1),
                    constraints_json=item.get("constraints"),
                    evidence_blocks=item.get("evidence_blocks") or [item["block_id"]],
                    is_questionable=is_questionable,
                    exclusion_reason=exclusion_reason if not is_questionable else None,
                    extraction_model=item.get("extraction_model"),
                    extraction_confidence=item.get("extraction_confidence"),
                    review_status=item.get("review_status", "candidate"),
                    embedding_vector=item.get("embedding_vector"),
                )
                session.add(row)
                rows.append(row)
            session.flush()
            ids = [row.eiu_id for row in rows]
            session.commit()
        return ids

    def delete_eius_all(self) -> int:
        """全量重抽前清空所有旧 EIU（覆盖式重算）。返回删除条数。"""
        with SessionLocal() as session:
            result = session.query(EiuRow).delete()
            session.commit()
            return int(result)

    def delete_eius_by_document(self, *, document_id: int) -> int:
        """单文档重抽前仅清空该文档的旧 EIU（按文档隔离，不影响其他文档）。返回删除条数。"""
        with SessionLocal() as session:
            block_ids = [
                row.block_id
                for row in session.query(BlockRow.block_id)
                .filter(BlockRow.document_id == document_id)
                .all()
            ]
            if not block_ids:
                return 0
            result = (
                session.query(EiuRow)
                .filter(EiuRow.block_id.in_(block_ids))
                .delete()
            )
            session.commit()
            return int(result)

    def list_eius(
        self,
        *,
        eiu_type: list[str] | None = None,
        priority: list[str] | None = None,
        questionable: bool | None = None,
        section: str | None = None,
        document_id: int | None = None,
        include_blocked: bool = False,
    ) -> list[dict]:
        with SessionLocal() as session:
            query = (
                session.query(EiuRow, BlockRow, DocumentRow)
                .join(BlockRow, EiuRow.block_id == BlockRow.block_id)
                .join(DocumentRow, BlockRow.document_id == DocumentRow.document_id)
            )
            if not include_blocked:
                query = query.filter(EiuRow.review_status != "blocked")
            if eiu_type:
                query = query.filter(EiuRow.eiu_type.in_(eiu_type))
            if priority:
                query = query.filter(EiuRow.content_priority.in_(priority))
            if questionable is not None:
                query = query.filter(EiuRow.is_questionable == bool(questionable))
            if section:
                query = query.filter(BlockRow.section_path.contains(section))
            if document_id is not None:
                query = query.filter(EiuRow.document_id == document_id)
            rows = query.order_by(EiuRow.eiu_id.asc()).all()
            return [self._eiu_to_dict(eiu, block, document) for eiu, block, document in rows]

    @staticmethod
    def _get_eiu_joined(session: Session, eiu_id: int) -> tuple[EiuRow, BlockRow, DocumentRow] | None:
        """按 eiu_id 联表查询，返回 (eiu, block, document)。"""
        return (
            session.query(EiuRow, BlockRow, DocumentRow)
            .join(BlockRow, EiuRow.block_id == BlockRow.block_id)
            .join(DocumentRow, BlockRow.document_id == DocumentRow.document_id)
            .filter(EiuRow.eiu_id == eiu_id)
            .first()
        )

    def get_eiu(self, eiu_id: int) -> dict | None:
        """EIU 详情，含原文上下文（prev / current / next Block 文本）。"""
        with SessionLocal() as session:
            row = self._get_eiu_joined(session, eiu_id)
            if not row:
                return None
            eiu, block, document = row
            siblings = (
                session.query(BlockRow)
                .filter(BlockRow.document_id == block.document_id)
                .order_by(BlockRow.block_id.asc())
                .all()
            )
            index = next((i for i, b in enumerate(siblings) if b.block_id == block.block_id), 0)
            result = self._eiu_to_dict(eiu, block, document)
            result["context"] = {
                "document_name": document.file_name,
                "section_path": block.section_path,
                "prev_text": siblings[index - 1].block_text if index > 0 else "",
                "block_text": block.block_text,
                "next_text": siblings[index + 1].block_text if index + 1 < len(siblings) else "",
            }
            return result

    def update_eiu(self, eiu_id: int, **updates: object) -> dict | None:
        with SessionLocal() as session:
            row = session.get(EiuRow, eiu_id)
            if not row:
                return None
            for field, value in updates.items():
                setattr(row, field, value)
            session.commit()
            joined = self._get_eiu_joined(session, eiu_id)
            if joined is None:
                return self._eiu_to_dict(row)
            eiu, block, document = joined
            return self._eiu_to_dict(eiu, block, document)

    def mark_eiu_blocked(self, eiu_id: int) -> dict | None:
        """DELETE 软删除：review_status=blocked，不再计入覆盖率分母。"""
        with SessionLocal() as session:
            row = session.get(EiuRow, eiu_id)
            if not row:
                return None
            row.review_status = "blocked"
            row.is_questionable = False
            session.commit()
            joined = self._get_eiu_joined(session, eiu_id)
            if joined is None:
                return self._eiu_to_dict(row)
            eiu, block, document = joined
            return self._eiu_to_dict(eiu, block, document)

    # ------------------------------------------------------------------
    # m05 — dataset_version / eval_case
    # ------------------------------------------------------------------
    def save_dataset_version(
        self,
        *,
        version_number: str,
        status: str = "draft",
        case_count: int = 0,
        coverage_report_id: int | None = None,
        split_config: dict | None = None,
        snapshot_metadata: dict | None = None,
    ) -> int:
        with SessionLocal() as session:
            row = DatasetVersionRow(
                version_number=version_number,
                status=status,
                case_count=case_count,
                coverage_report_id=coverage_report_id,
                split_config=split_config,
                snapshot_metadata=snapshot_metadata,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row.version_id

    def list_dataset_versions(self) -> list[dict]:
        with SessionLocal() as session:
            rows = (
                session.query(DatasetVersionRow)
                .order_by(DatasetVersionRow.version_id.desc())
                .all()
            )
            return [
                {
                    "version_id": row.version_id,
                    "version_number": row.version_number,
                    "status": row.status,
                    "case_count": row.case_count,
                    "coverage_report_id": row.coverage_report_id,
                    "split_config": row.split_config,
                    "snapshot_metadata": row.snapshot_metadata,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "frozen_at": row.frozen_at.isoformat() if row.frozen_at else None,
                }
                for row in rows
            ]

    def get_dataset_version(self, version_id: int) -> dict | None:
        with SessionLocal() as session:
            row = session.get(DatasetVersionRow, version_id)
            if not row:
                return None
            return {
                "version_id": row.version_id,
                "version_number": row.version_number,
                "status": row.status,
                "case_count": row.case_count,
                "coverage_report_id": row.coverage_report_id,
                "split_config": row.split_config,
                "snapshot_metadata": row.snapshot_metadata,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "frozen_at": row.frozen_at.isoformat() if row.frozen_at else None,
            }

    def update_dataset_version(
        self,
        version_id: int,
        *,
        status: str | None = None,
        case_count: int | None = None,
        snapshot_metadata: dict | None = None,
        freeze: bool = False,
    ) -> None:
        with SessionLocal() as session:
            row = session.get(DatasetVersionRow, version_id)
            if not row:
                return
            if status is not None:
                row.status = status
            if case_count is not None:
                row.case_count = case_count
            if snapshot_metadata is not None:
                row.snapshot_metadata = snapshot_metadata
            if freeze:
                row.frozen_at = datetime.utcnow()
            session.commit()

    def get_latest_version_number(self) -> str | None:
        with SessionLocal() as session:
            row = (
                session.query(DatasetVersionRow)
                .order_by(DatasetVersionRow.version_id.desc())
                .first()
            )
            return row.version_number if row else None

    def save_eval_case(
        self,
        *,
        version_id: int,
        case_uid: str,
        question: str,
        intent_id: str | None = None,
        type: str | None = None,
        scope: str | None = None,
        difficulty: str | None = None,
        gold_answer: str | None = None,
        must_have_points: list | None = None,
        acceptable_answers: list | None = None,
        evidence: list | None = None,
        eiu_ids: list | None = None,
        content_priority: str | None = None,
        review_status: str = "candidate",
        source: str = "native",
    ) -> int:
        with SessionLocal() as session:
            row = EvalCaseRow(
                version_id=version_id,
                case_uid=case_uid,
                intent_id=intent_id,
                question=question,
                type=type,
                scope=scope,
                difficulty=difficulty,
                gold_answer=gold_answer,
                must_have_points=must_have_points,
                acceptable_answers=acceptable_answers,
                evidence=evidence,
                eiu_ids=eiu_ids,
                content_priority=content_priority,
                review_status=review_status,
                source=source,
                retired=False,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row.case_id

    def get_eval_cases(
        self,
        version_id: int,
        *,
        include_retired: bool = False,
        source: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict]:
        with SessionLocal() as session:
            query = session.query(EvalCaseRow).filter(EvalCaseRow.version_id == version_id)
            if not include_retired:
                query = query.filter(EvalCaseRow.retired.is_(False))
            if source is not None:
                query = query.filter(EvalCaseRow.source == source)
            rows = (
                query.order_by(EvalCaseRow.case_id.asc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return [self._eval_case_to_dict(row) for row in rows]

    def count_eval_cases(self, version_id: int, *, include_retired: bool = False) -> int:
        with SessionLocal() as session:
            query = session.query(EvalCaseRow).filter(EvalCaseRow.version_id == version_id)
            if not include_retired:
                query = query.filter(EvalCaseRow.retired.is_(False))
            return query.count()

    def get_eval_case(self, case_id: int) -> dict | None:
        with SessionLocal() as session:
            row = session.get(EvalCaseRow, case_id)
            return self._eval_case_to_dict(row) if row else None

    def update_eval_case(
        self,
        case_id: int,
        *,
        question: str | None = None,
        gold_answer: str | None = None,
        type: str | None = None,
        scope: str | None = None,
        difficulty: str | None = None,
        content_priority: str | None = None,
        must_have_points: list | None = None,
        acceptable_answers: list | None = None,
        evidence: list | None = None,
    ) -> None:
        with SessionLocal() as session:
            row = session.get(EvalCaseRow, case_id)
            if not row:
                return
            if question is not None:
                row.question = question
            if gold_answer is not None:
                row.gold_answer = gold_answer
            if type is not None:
                row.type = type
            if scope is not None:
                row.scope = scope
            if difficulty is not None:
                row.difficulty = difficulty
            if content_priority is not None:
                row.content_priority = content_priority
            if must_have_points is not None:
                row.must_have_points = must_have_points
            if acceptable_answers is not None:
                row.acceptable_answers = acceptable_answers
            if evidence is not None:
                row.evidence = evidence
            # 手动编辑后回退质量校验状态（复用 FR-DS-EDIT-001）
            row.review_status = "candidate"
            session.commit()

    def retire_eval_case(self, case_id: int) -> None:
        with SessionLocal() as session:
            row = session.get(EvalCaseRow, case_id)
            if not row:
                return
            row.retired = True
            session.commit()

    @staticmethod
    def _eval_case_to_dict(row: "EvalCaseRow") -> dict:
        return {
            "case_id": row.case_id,
            "version_id": row.version_id,
            "case_uid": row.case_uid,
            "intent_id": row.intent_id,
            "question": row.question,
            "type": row.type,
            "scope": row.scope,
            "difficulty": row.difficulty,
            "gold_answer": row.gold_answer,
            "must_have_points": row.must_have_points,
            "acceptable_answers": row.acceptable_answers,
            "evidence": row.evidence,
            "eiu_ids": row.eiu_ids,
            "content_priority": row.content_priority,
            "review_status": row.review_status,
            "source": row.source,
            "retired": row.retired,
        }

    # ------------------------------------------------------------------
    # m02 — coverage_report 快照（供 m05 冻结版本外键引用）
    # ------------------------------------------------------------------
    def save_coverage_report(
        self,
        *,
        total_eiu: int = 0,
        questionable_eiu: int = 0,
        excluded_eiu: int = 0,
        by_priority: dict | None = None,
        by_type: dict | None = None,
        by_document: list | None = None,
        by_section: list | None = None,
        weighted_coverage: float = 0.0,
        p0_coverage_pct: float = 0.0,
        block_reconciliation: dict | None = None,
        alerts: list | None = None,
        snapshot_metadata: dict | None = None,
    ) -> int:
        with SessionLocal() as session:
            row = CoverageReportRow(
                total_eiu=total_eiu,
                questionable_eiu=questionable_eiu,
                excluded_eiu=excluded_eiu,
                by_priority=by_priority,
                by_type=by_type,
                by_document=by_document,
                by_section=by_section,
                weighted_coverage=weighted_coverage,
                p0_coverage_pct=p0_coverage_pct,
                block_reconciliation=block_reconciliation,
                alerts=alerts,
                snapshot_metadata=snapshot_metadata,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row.report_id

    def get_latest_coverage_report(self) -> dict | None:
        with SessionLocal() as session:
            row = (
                session.query(CoverageReportRow)
                .order_by(CoverageReportRow.report_id.desc())
                .first()
            )
            if not row:
                return None
            return self._coverage_report_to_dict(row)

    @staticmethod
    def _coverage_report_to_dict(row: "CoverageReportRow") -> dict:
        return {
            "report_id": row.report_id,
            "total_eiu": row.total_eiu,
            "questionable_eiu": row.questionable_eiu,
            "excluded_eiu": row.excluded_eiu,
            "by_priority": row.by_priority,
            "by_type": row.by_type,
            "by_document": row.by_document,
            "by_section": row.by_section,
            "weighted_coverage": row.weighted_coverage,
            "p0_coverage_pct": row.p0_coverage_pct,
            "block_reconciliation": row.block_reconciliation,
            "alerts": row.alerts,
            "snapshot_metadata": row.snapshot_metadata,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    # ------------------------------------------------------------------
    # 追加：m03 评测集生成 / m04 质量治理（corpus 语义，独立于 m05 的 eval_case）
    # 说明：本组方法对应"智能评测集生成平台"m03/m04 的数据模型，
    #       使用独立表 generated_case / quality_check_result，
    #       与 m05 的 eval_case(version_id 语义) 并存互不干扰。
    # ------------------------------------------------------------------
    def save_generated_case(
        self,
        *,
        intent_id: str,
        eiu_id: int | None,
        document_id: int | None,
        question: str,
        question_type: str,
        difficulty: str,
        scope_type: str,
        gold_answer: str,
        must_have_points: list | None = None,
        acceptable_answers: list | None = None,
        evidence: list | None = None,
        content_priority: str = "P2",
        review_status: str = "candidate",
        statement_norm: str | None = None,
        folder_path: str | None = None,
        purpose: str | None = None,
    ) -> dict:
        """保存一条 m03 生成的评测样本（按文档维度组织）。

        statement_norm: 源 EIU statement 的归一化值（跨文件复用匹配键）。
        不传时留空（旧调用兼容）；调用方应在生成/复用落库时显式传入。
        folder_path / purpose：问答对库目录归属，默认继承源文档目录与用途。
        """
        with SessionLocal() as session:
            row = GeneratedCaseRow(
                intent_id=intent_id,
                eiu_id=eiu_id,
                document_id=document_id,
                question=question,
                question_type=question_type,
                difficulty=difficulty,
                scope_type=scope_type,
                gold_answer=gold_answer,
                must_have_points=must_have_points,
                acceptable_answers=acceptable_answers,
                evidence=evidence,
                content_priority=content_priority,
                review_status=review_status,
                statement_norm=statement_norm,
                folder_path=folder_path,
                purpose=purpose,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return self._generated_case_to_dict(row)

    def delete_generated_cases_by_document(
        self, *, document_id: int
    ) -> int:
        """删除指定文档下的全部 m03 评测样本（问答对单文档隔离，重抽前清理）。"""
        with SessionLocal() as session:
            rows = (
                session.query(GeneratedCaseRow)
                .filter_by(document_id=document_id)
                .all()
            )
            for row in rows:
                session.delete(row)
            session.commit()
            return len(rows)

    def find_cases_by_statement(
        self, statement_norm: str
    ) -> list[dict]:
        """跨文件精确匹配：按归一化 statement 查找已有问答对（复用）。

        用于"重合内容复用旧问答对"——不同文件中出现相同 EIU 陈述时，
        直接复用历史生成的规范问答对，跳过 LLM 重生成。
        """
        if not statement_norm:
            return []
        with SessionLocal() as session:
            row = (
                session.query(GeneratedCaseRow)
                .filter_by(statement_norm=statement_norm)
                .order_by(GeneratedCaseRow.case_id.desc())
                .first()
            )
            return [self._generated_case_to_dict(row)] if row else []

    def find_similar_cases(
        self, statement: str, threshold: float = 0.92
    ) -> list[dict]:
        """语义复用：用 BGE 编码 statement，检索全库历史 case 中语义相近者。

        与 find_cases_by_statement（归一化精确匹配）互补——
        精确匹配只能命中"措辞完全一致"的陈述，本方法可命中"语义相同但
        措辞不同"的历史知识点，从而复用已生成的规范问答对、跳过 LLM 重生成。

        无本地 embedding 模型（离线）时优雅降级为空列表（不阻断主流程）。
        """
        if not statement:
            return []
        try:
            from modules.m01_data_foundation.services.embedding import (
                EmbeddingService,
            )

            embedder = EmbeddingService()
            (qvec,) = embedder.embed_texts([statement], is_query=True)
        except Exception as exc:  # 离线/无模型：跳过语义复用
            logger.warning("语义复用跳过（embedding 不可用）：%s", exc)
            return []

        with SessionLocal() as session:
            rows = (
                session.query(GeneratedCaseRow)
                .filter(GeneratedCaseRow.statement_norm.isnot(None))
                .all()
            )
        best: dict | None = None
        best_score = threshold
        for row in rows:
            norm = row.statement_norm
            if not norm:
                continue
            try:
                (cvec,) = embedder.embed_texts([norm])
            except Exception:
                continue
            # 已是 unit 向量（normalize_embeddings=True），内积=余弦相似度
            score = float(sum(a * b for a, b in zip(qvec, cvec)))
            if score >= best_score:
                best_score = score
                best = self._generated_case_to_dict(row)
        if best is not None:
            best = dict(best)
            best["similarity"] = round(best_score, 4)
        return [best] if best else []

    def dedup_exact_cases(self, cases: list[dict]) -> dict:
        """精确查重：按归一化 question 哈希，去掉「一模一样」的问题。

        与 find_similar_cases（语义）不同，本方法只抓"去除格式差异后完全相同"的
        问题（空格/全半角/尾部标点/大小写不同视为同一题），不误伤相似但不同的问题。

        返回：
          keep: 保留的 case（同 key 只留第一个）
          duplicate: 被判定为重复的 case（含 reason）
        """
        seen: dict[str, int] = {}  # norm_key -> 保留的 case index
        keep: list[dict] = []
        duplicate: list[dict] = []
        for case in cases:
            q = (case.get("question") or "").strip()
            key = normalize_question(q) if q else ""
            if not key:
                keep.append(case)
                continue
            if key in seen:
                dup = dict(case)
                dup["duplicate_reason"] = "问题与已有评测项重复（归一化一致）"
                duplicate.append(dup)
            else:
                seen[key] = len(keep)
                keep.append(case)
        return {"keep": keep, "duplicate": duplicate}

    def list_generated_cases(
        self,
        *,
        document_id: int | None = None,
        priority: str | None = None,
        question_type: str | None = None,
        difficulty: str | None = None,
        status: str | None = None,
        folder_path: str | None = None,
        purpose: str | None = None,
    ) -> list[dict]:
        """查询 m03 生成的评测样本；默认排除 retired。按 document / 目录 / 用途过滤。"""
        with SessionLocal() as session:
            query = session.query(GeneratedCaseRow)
            if document_id is not None:
                query = query.filter(GeneratedCaseRow.document_id == document_id)
            if folder_path is not None:
                query = query.filter(GeneratedCaseRow.folder_path == folder_path)
            if purpose is not None:
                query = query.filter(GeneratedCaseRow.purpose == purpose)
            if priority is not None:
                query = query.filter(GeneratedCaseRow.content_priority == priority)
            if question_type is not None:
                query = query.filter(GeneratedCaseRow.question_type == question_type)
            if difficulty is not None:
                query = query.filter(GeneratedCaseRow.difficulty == difficulty)
            if status is not None:
                query = query.filter(GeneratedCaseRow.review_status == status)
            else:
                query = query.filter(GeneratedCaseRow.review_status != "retired")
            rows = query.order_by(GeneratedCaseRow.case_id.desc()).all()
            return [self._generated_case_to_dict(row) for row in rows]

    def get_generated_case(self, case_id: int) -> dict | None:
        """查询单条 m03 评测样本。"""
        with SessionLocal() as session:
            row = session.get(GeneratedCaseRow, case_id)
            return self._generated_case_to_dict(row) if row else None

    def update_generated_case(
        self,
        case_id: int,
        *,
        question: str | None = None,
        question_type: str | None = None,
        difficulty: str | None = None,
        gold_answer: str | None = None,
        must_have_points: list | None = None,
        acceptable_answers: list | None = None,
        evidence: list | None = None,
        content_priority: str | None = None,
        review_status: str | None = None,
        review_tag: str | None = None,
        folder_path: str | None = None,
        purpose: str | None = None,
    ) -> dict | None:
        """更新单条 m03 评测样本（含 m04 状态机字段与目录归属）。"""
        with SessionLocal() as session:
            row = session.get(GeneratedCaseRow, case_id)
            if not row:
                return None
            if question is not None:
                row.question = question
            if question_type is not None:
                row.question_type = question_type
            if difficulty is not None:
                row.difficulty = difficulty
            if gold_answer is not None:
                row.gold_answer = gold_answer
            if must_have_points is not None:
                row.must_have_points = must_have_points
            if acceptable_answers is not None:
                row.acceptable_answers = acceptable_answers
            if evidence is not None:
                row.evidence = evidence
            if content_priority is not None:
                row.content_priority = content_priority
            if review_status is not None:
                row.review_status = review_status
            if review_tag is not None:
                row.review_tag = review_tag
            if folder_path is not None:
                row.folder_path = folder_path
            if purpose is not None:
                row.purpose = purpose
            session.commit()
            session.refresh(row)
            return self._generated_case_to_dict(row)

    def retire_generated_case(self, case_id: int) -> bool:
        """删除 = 标记 retired，保留审计痕迹。"""
        updated = self.update_generated_case(case_id, review_status="retired")
        return updated is not None

    def list_covered_eiu_ids(
        self,
        *,
        document_id: int | None = None,
        statuses: set[str] | None = None,
    ) -> set[int]:
        """已生成评测样本的 EIU id 集合（按文档维度）。

        传入 document_id 时仅返回该文档维度的已覆盖 EIU，
        实现单文档问答对隔离——重抽某文档不会误判其他文档已覆盖项。
        statuses 非空时仅统计处于指定审核状态的样本（如"可发布态"），
        用于覆盖率 / gaps 口径；m03 生成侧不传 statuses（保持跳过已覆盖项）。
        """
        with SessionLocal() as session:
            query = (
                session.query(GeneratedCaseRow.eiu_id)
                .filter(GeneratedCaseRow.eiu_id.isnot(None))
                .filter(GeneratedCaseRow.review_status != "retired")
            )
            if statuses:
                query = query.filter(GeneratedCaseRow.review_status.in_(statuses))
            if document_id is not None:
                query = query.filter(GeneratedCaseRow.document_id == document_id)
            rows = query.all()
            return {row[0] for row in rows}

    # ------------------------------------------------------------------
    # m04 质量检查结果（quality_check_result 表）
    # ------------------------------------------------------------------
    def clear_quality_checks(self, case_id: int) -> None:
        """重跑质检前清空该 case 的历史结果。"""
        with SessionLocal() as session:
            session.query(QualityCheckRow).filter(
                QualityCheckRow.case_id == case_id
            ).delete(synchronize_session=False)
            session.commit()

    def save_quality_check(
        self,
        *,
        case_id: int,
        check_type: str,
        passed: bool,
        reason: str,
    ) -> dict:
        """保存单条检查结果。"""
        with SessionLocal() as session:
            row = QualityCheckRow(
                case_id=case_id,
                check_type=check_type,
                passed=1 if passed else 0,
                reason=reason or "",
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return self._quality_check_to_dict(row)

    def replace_quality_checks(self, *, case_id: int, checks: list[dict]) -> list[dict]:
        """原子替换单个 case 的质量检查结果。"""
        with SessionLocal() as session:
            session.query(QualityCheckRow).filter(
                QualityCheckRow.case_id == case_id
            ).delete(synchronize_session=False)
            rows = [
                QualityCheckRow(
                    case_id=case_id,
                    check_type=check["check_type"],
                    passed=1 if check["passed"] else 0,
                    reason=check["reason"] or "",
                )
                for check in checks
            ]
            session.add_all(rows)
            session.commit()
            for row in rows:
                session.refresh(row)
            return [self._quality_check_to_dict(row) for row in rows]

    def list_quality_checks(self, case_id: int) -> list[dict]:
        """查询单个 case 的全部检查结果。"""
        with SessionLocal() as session:
            rows = (
                session.query(QualityCheckRow)
                .filter(QualityCheckRow.case_id == case_id)
                .order_by(QualityCheckRow.check_id)
                .all()
            )
            return [self._quality_check_to_dict(row) for row in rows]

    def list_quality_checks_by_document(self, document_id: int | None = None) -> list[dict]:
        """查询全部/指定文档下检查结果（join generated_case 按 document 过滤，跳过 retired）。"""
        with SessionLocal() as session:
            query = (
                session.query(QualityCheckRow)
                .join(GeneratedCaseRow, QualityCheckRow.case_id == GeneratedCaseRow.case_id)
                .filter(GeneratedCaseRow.review_status != "retired")
            )
            if document_id is not None:
                query = query.filter(GeneratedCaseRow.document_id == document_id)
            rows = query.all()
            return [self._quality_check_to_dict(row) for row in rows]

    @staticmethod
    def _quality_check_to_dict(row: "QualityCheckRow") -> dict:
        return {
            "check_id": row.check_id,
            "case_id": row.case_id,
            "check_type": row.check_type,
            "passed": bool(row.passed),
            "reason": row.reason,
            "checked_at": row.checked_at.isoformat() if row.checked_at else None,
        }

    @staticmethod
    def _generated_case_to_dict(row: "GeneratedCaseRow") -> dict:
        return {
            "case_id": row.case_id,
            "intent_id": row.intent_id,
            "eiu_id": row.eiu_id,
            "document_id": row.document_id,
            "question": row.question,
            "question_type": row.question_type,
            "difficulty": row.difficulty,
            "scope_type": row.scope_type,
            "gold_answer": row.gold_answer,
            "must_have_points": row.must_have_points,
            "acceptable_answers": row.acceptable_answers,
            "evidence": row.evidence,
            "content_priority": row.content_priority,
            "folder_path": row.folder_path,
            "purpose": row.purpose,
            "review_status": row.review_status,
            "review_tag": row.review_tag,
            "statement_norm": row.statement_norm,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    # ------------------------------------------------------------------
    # m05 — 上传评测集（BRD §8.22 FR-DS-SRC-001/002/003/006）
    # ------------------------------------------------------------------
    def save_uploaded_set(
        self,
        *,
        name: str,
        template_type: str = "single",
        source_file: str | None = None,
        dimension: str | None = None,
    ) -> int:
        with SessionLocal() as session:
            row = UploadedEvalSetRow(
                name=name,
                template_type=template_type,
                source_file=source_file,
                dimension=dimension,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row.set_id

    def create_uploaded_set_with_cases(
        self,
        *,
        name: str,
        template_type: str,
        source_file: str | None,
        dimension: str | None,
        cases: list[dict],
        quality_snapshot: dict,
    ) -> dict:
        """在同一事务内保存上传集、样本与质量快照。"""
        with SessionLocal() as session:
            row = UploadedEvalSetRow(
                name=name,
                template_type=template_type,
                source_file=source_file,
                dimension=dimension,
                review_status="quality_checked",
                quality_snapshot=quality_snapshot,
                total_cases=len(cases),
            )
            session.add(row)
            session.flush()
            for case in cases:
                session.add(
                    UploadedEvalCaseRow(
                        set_id=row.set_id,
                        q=str(case["q"]),
                        a=str(case["a"]),
                        evidence=case.get("evidence"),
                        dimension=case.get("dimension"),
                        session_id=case.get("session_id"),
                        turns=case.get("turns"),
                        key_turn=case.get("key_turn"),
                        turn_type=case.get("turn_type"),
                        depends_on_turns=case.get("depends_on_turns"),
                        no_evidence=1 if not case.get("evidence") else 0,
                        quality=case.get("quality"),
                        review_status="quality_checked",
                    )
                )
            session.commit()
            session.refresh(row)
            return {
                "set_id": row.set_id,
                "quality": quality_snapshot,
                "total_cases": len(cases),
            }

    def list_uploaded_sets(self) -> list[dict]:
        with SessionLocal() as session:
            rows = (
                session.query(UploadedEvalSetRow)
                .order_by(UploadedEvalSetRow.set_id.desc())
                .all()
            )
            return [self._uploaded_set_to_dict(r) for r in rows]

    def get_uploaded_set(self, set_id: int) -> dict | None:
        with SessionLocal() as session:
            row = session.get(UploadedEvalSetRow, set_id)
            return self._uploaded_set_to_dict(row) if row else None

    def update_uploaded_set(self, set_id: int, **updates: object) -> dict | None:
        with SessionLocal() as session:
            row = session.get(UploadedEvalSetRow, set_id)
            if not row:
                return None
            for key, value in updates.items():
                if hasattr(row, key) and value is not None:
                    setattr(row, key, value)
            session.commit()
            session.refresh(row)
            return self._uploaded_set_to_dict(row)

    def delete_uploaded_set(self, set_id: int) -> None:
        with SessionLocal() as session:
            session.query(UploadedEvalCaseRow).filter(
                UploadedEvalCaseRow.set_id == set_id
            ).delete(synchronize_session=False)
            session.query(UploadedEvalSetRow).filter(
                UploadedEvalSetRow.set_id == set_id
            ).delete(synchronize_session=False)
            session.commit()

    def save_uploaded_cases(self, *, set_id: int, cases: list[dict]) -> int:
        with SessionLocal() as session:
            for case in cases:
                session.add(
                    UploadedEvalCaseRow(
                        set_id=set_id,
                        q=str(case["q"]),
                        a=str(case["a"]),
                        evidence=case.get("evidence"),
                        dimension=case.get("dimension"),
                        session_id=case.get("session_id"),
                        turns=case.get("turns"),
                        key_turn=case.get("key_turn"),
                        turn_type=case.get("turn_type"),
                        depends_on_turns=case.get("depends_on_turns"),
                        no_evidence=1 if not case.get("evidence") else 0,
                        quality=case.get("quality"),
                        review_status=case.get("review_status", "pending"),
                    )
                )
            session.commit()
            return len(cases)

    def list_uploaded_cases(self, set_id: int) -> list[dict]:
        with SessionLocal() as session:
            rows = (
                session.query(UploadedEvalCaseRow)
                .filter(UploadedEvalCaseRow.set_id == set_id)
                .order_by(UploadedEvalCaseRow.case_id)
                .all()
            )
            return [self._uploaded_case_to_dict(r) for r in rows]

    @staticmethod
    def _uploaded_set_to_dict(row: "UploadedEvalSetRow") -> dict:
        return {
            "set_id": row.set_id,
            "name": row.name,
            "template_type": row.template_type,
            "source_file": row.source_file,
            "dimension": row.dimension,
            "review_status": row.review_status,
            "quality_snapshot": row.quality_snapshot,
            "total_cases": row.total_cases,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    @staticmethod
    def _uploaded_case_to_dict(row: "UploadedEvalCaseRow") -> dict:
        return {
            "case_id": row.case_id,
            "set_id": row.set_id,
            "q": row.q,
            "a": row.a,
            "evidence": row.evidence,
            "dimension": row.dimension,
            "session_id": row.session_id,
            "turns": row.turns,
            "key_turn": row.key_turn,
            "turn_type": row.turn_type,
            "depends_on_turns": row.depends_on_turns,
            "no_evidence": bool(row.no_evidence),
            "quality": row.quality,
            "review_status": row.review_status,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    # ------------------------------------------------------------------
    # m05 — 公共评测集库 / 维度（BRD §8.22 FR-DS-SRC-004）
    # ------------------------------------------------------------------
    def save_public_set(
        self,
        *,
        name: str,
        version: str = "v1.0.0",
        dimensions: list | None = None,
        review_status: str = "quality_checked",
    ) -> int:
        with SessionLocal() as session:
            row = PublicEvalSetRow(
                name=name,
                version=version,
                dimensions=dimensions,
                review_status=review_status,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row.set_id

    def list_public_sets(self, *, include_retired: bool = False) -> list[dict]:
        with SessionLocal() as session:
            query = session.query(PublicEvalSetRow).order_by(PublicEvalSetRow.set_id.desc())
            if not include_retired:
                query = query.filter(PublicEvalSetRow.status == "active")
            return [self._public_set_to_dict(r) for r in query.all()]

    def get_public_set(self, set_id: int) -> dict | None:
        with SessionLocal() as session:
            row = session.get(PublicEvalSetRow, set_id)
            return self._public_set_to_dict(row) if row else None

    def update_public_set(self, set_id: int, **updates: object) -> dict | None:
        with SessionLocal() as session:
            row = session.get(PublicEvalSetRow, set_id)
            if not row:
                return None
            for key, value in updates.items():
                if hasattr(row, key) and value is not None:
                    setattr(row, key, value)
            session.commit()
            session.refresh(row)
            return self._public_set_to_dict(row)

    def save_public_cases(self, *, set_id: int, cases: list[dict]) -> int:
        with SessionLocal() as session:
            for case in cases:
                session.add(
                    PublicEvalCaseRow(
                        set_id=set_id,
                        q=str(case["q"]),
                        a=str(case["a"]),
                        evidence=case.get("evidence"),
                        dimension=case.get("dimension"),
                        no_evidence=1 if not case.get("evidence") else 0,
                        review_status="quality_checked",
                    )
                )
            session.commit()
            return len(cases)

    def list_public_cases(self, set_id: int) -> list[dict]:
        with SessionLocal() as session:
            rows = (
                session.query(PublicEvalCaseRow)
                .filter(PublicEvalCaseRow.set_id == set_id)
                .order_by(PublicEvalCaseRow.case_id)
                .all()
            )
            return [self._public_case_to_dict(r) for r in rows]

    @staticmethod
    def _public_set_to_dict(row: "PublicEvalSetRow") -> dict:
        return {
            "set_id": row.set_id,
            "name": row.name,
            "version": row.version,
            "dimensions": row.dimensions,
            "review_status": row.review_status,
            "quality_snapshot": row.quality_snapshot,
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def _public_case_to_dict(row: "PublicEvalCaseRow") -> dict:
        return {
            "case_id": row.case_id,
            "set_id": row.set_id,
            "q": row.q,
            "a": row.a,
            "evidence": row.evidence,
            "dimension": row.dimension,
            "no_evidence": bool(row.no_evidence),
            "review_status": row.review_status,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    def list_dimensions(self) -> list[dict]:
        with SessionLocal() as session:
            rows = (
                session.query(EvalSetDimensionRow)
                .filter(EvalSetDimensionRow.enabled == 1)
                .order_by(EvalSetDimensionRow.dimension_id)
                .all()
            )
            return [self._dimension_to_dict(r) for r in rows]

    def save_dimension(self, *, code: str, name: str, description: str | None = None) -> int:
        with SessionLocal() as session:
            row = EvalSetDimensionRow(code=code, name=name, description=description)
            session.add(row)
            session.commit()
            session.refresh(row)
            return row.dimension_id

    @staticmethod
    def _dimension_to_dict(row: "EvalSetDimensionRow") -> dict:
        return {
            "dimension_id": row.dimension_id,
            "code": row.code,
            "name": row.name,
            "description": row.description,
            "enabled": bool(row.enabled),
        }

    # ------------------------------------------------------------------
    # m05 — 评测集组合选择（BRD §8.22 FR-DS-SRC-005）
    # ------------------------------------------------------------------
    def save_composition(self, *, name: str, items: list[dict], created_by: str | None = None) -> int:
        with SessionLocal() as session:
            row = EvalSetCompositionRow(name=name, items=items, created_by=created_by)
            session.add(row)
            session.commit()
            session.refresh(row)
            return row.composition_id

    def list_compositions(self) -> list[dict]:
        with SessionLocal() as session:
            rows = (
                session.query(EvalSetCompositionRow)
                .order_by(EvalSetCompositionRow.composition_id.desc())
                .all()
            )
            return [self._composition_to_dict(r) for r in rows]

    def get_composition(self, composition_id: int) -> dict | None:
        with SessionLocal() as session:
            row = session.get(EvalSetCompositionRow, composition_id)
            return self._composition_to_dict(row) if row else None

    def delete_composition(self, composition_id: int) -> None:
        with SessionLocal() as session:
            session.query(EvalSetCompositionRow).filter(
                EvalSetCompositionRow.composition_id == composition_id
            ).delete(synchronize_session=False)
            session.commit()

    @staticmethod
    def _composition_to_dict(row: "EvalSetCompositionRow") -> dict:
        return {
            "composition_id": row.composition_id,
            "name": row.name,
            "items": row.items,
            "created_by": row.created_by,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    # ------------------------------------------------------------------
    # m08 — Agent 评测运行 / 单题结果 / ErrorBook（BRD §9）
    # ------------------------------------------------------------------
    def save_evaluation_run(
        self,
        *,
        composition_id: int | None,
        name: str | None,
        adapter: str,
        adapter_config: dict | None = None,
    ) -> int:
        with SessionLocal() as session:
            row = EvaluationRunRow(
                composition_id=composition_id,
                name=name,
                adapter=adapter,
                adapter_config=adapter_config,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row.run_id

    def get_evaluation_run(self, run_id: int) -> dict | None:
        with SessionLocal() as session:
            row = session.get(EvaluationRunRow, run_id)
            return self._evaluation_run_to_dict(row) if row else None

    def list_evaluation_runs(self) -> list[dict]:
        with SessionLocal() as session:
            rows = (
                session.query(EvaluationRunRow)
                .order_by(EvaluationRunRow.run_id.desc())
                .all()
            )
            return [self._evaluation_run_to_dict(r) for r in rows]

    def update_evaluation_run(self, run_id: int, **updates: object) -> dict | None:
        with SessionLocal() as session:
            row = session.get(EvaluationRunRow, run_id)
            if not row:
                return None
            for key, value in updates.items():
                if hasattr(row, key) and value is not None:
                    setattr(row, key, value)
            session.commit()
            session.refresh(row)
            return self._evaluation_run_to_dict(row)

    def save_evaluation_case_result(self, *, run_id: int, **fields: object) -> int:
        with SessionLocal() as session:
            row = EvaluationCaseResultRow(run_id=run_id, **fields)
            session.add(row)
            session.commit()
            session.refresh(row)
            return row.result_id

    def list_evaluation_results(self, run_id: int) -> list[dict]:
        with SessionLocal() as session:
            rows = (
                session.query(EvaluationCaseResultRow)
                .filter(EvaluationCaseResultRow.run_id == run_id)
                .order_by(EvaluationCaseResultRow.result_id)
                .all()
            )
            return [self._evaluation_result_to_dict(r) for r in rows]

    def save_error_book_item(
        self,
        *,
        run_id: int | None,
        case_uid: str | None,
        diagnosis: str,
        root_cause: str | None = None,
        optimization: str | None = None,
        regression: list | None = None,
    ) -> int:
        with SessionLocal() as session:
            row = ErrorBookItemRow(
                run_id=run_id,
                case_uid=case_uid,
                diagnosis=diagnosis,
                root_cause=root_cause,
                optimization=optimization,
                regression=regression,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row.item_id

    def list_error_book(
        self,
        *,
        run_id: int | None = None,
        diagnosis: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        with SessionLocal() as session:
            query = session.query(ErrorBookItemRow).order_by(ErrorBookItemRow.item_id.desc())
            if run_id is not None:
                query = query.filter(ErrorBookItemRow.run_id == run_id)
            if diagnosis:
                query = query.filter(ErrorBookItemRow.diagnosis == diagnosis)
            if status:
                query = query.filter(ErrorBookItemRow.status == status)
            return [self._error_book_to_dict(r) for r in query.all()]

    def update_error_book_item(self, item_id: int, **updates: object) -> dict | None:
        with SessionLocal() as session:
            row = session.get(ErrorBookItemRow, item_id)
            if not row:
                return None
            for key, value in updates.items():
                if hasattr(row, key) and value is not None:
                    setattr(row, key, value)
            session.commit()
            session.refresh(row)
            return self._error_book_to_dict(row)

    @staticmethod
    def _evaluation_run_to_dict(row: "EvaluationRunRow") -> dict:
        adapter_config = dict(row.adapter_config or {})
        # 安全：不回显 API Key 等敏感配置
        if "api_key" in adapter_config:
            adapter_config["api_key"] = "***"
        return {
            "run_id": row.run_id,
            "composition_id": row.composition_id,
            "name": row.name,
            "adapter": row.adapter,
            "adapter_config": adapter_config,
            "status": row.status,
            "progress": row.progress,
            "total": row.total,
            "finished": row.finished,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    @staticmethod
    def _evaluation_result_to_dict(row: "EvaluationCaseResultRow") -> dict:
        return {
            "result_id": row.result_id,
            "run_id": row.run_id,
            "case_uid": row.case_uid,
            "question": row.question,
            "gold_answer": row.gold_answer,
            "difficulty": row.difficulty,
            "dimension": row.dimension,
            "source": row.source,
            "answer": row.answer,
            "turn_outputs": row.turn_outputs,
            "retrieved": row.retrieved,
            "scores": row.scores,
            "diagnosis": row.diagnosis,
            "status": row.status,
            "error_message": row.error_message,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    @staticmethod
    def _error_book_to_dict(row: "ErrorBookItemRow") -> dict:
        return {
            "item_id": row.item_id,
            "run_id": row.run_id,
            "case_uid": row.case_uid,
            "diagnosis": row.diagnosis,
            "root_cause": row.root_cause,
            "optimization": row.optimization,
            "regression": row.regression,
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }


class GeneratedCaseRow(Base):
    """m03 生成的评测样本（按文档维度组织，独立于 m05 的 eval_case 表）。"""

    __tablename__ = "generated_case"

    case_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    intent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    eiu_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 用户上传路径可无 EIU
    document_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[str] = mapped_column(String(64), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(64), nullable=False)
    gold_answer: Mapped[str] = mapped_column(Text, nullable=False)
    must_have_points: Mapped[list | None] = mapped_column(JSON, nullable=True)
    acceptable_answers: Mapped[list | None] = mapped_column(JSON, nullable=True)
    evidence: Mapped[list | None] = mapped_column(JSON, nullable=True)
    content_priority: Mapped[str] = mapped_column(String(8), nullable=False)
    # 目录结构：相对「问答对库」根路径（如「基础问题/子A」），根目录为空
    folder_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # 业务用途：basic=基础问题，gen=泛化问题；与 document.purpose 同语义
    purpose: Mapped[str | None] = mapped_column(String(16), nullable=True)
    review_status: Mapped[str] = mapped_column(
        String(64), nullable=False, default="candidate"
    )
    # m04 质量门禁失败标签：answer_coverage / generation_issue
    review_tag: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 方案 B 复用匹配键：源 EIU statement 归一化值（跨语料库精确匹配）
    statement_norm: Mapped[str | None] = mapped_column(
        String(512), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class QualityCheckRow(Base):
    """单题质量检查结果（m04 产出）。"""

    __tablename__ = "quality_check_result"

    check_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    check_type: Mapped[str] = mapped_column(String(64), nullable=False)
    passed: Mapped[bool] = mapped_column(Integer, nullable=False, default=1)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ----------------------------------------------------------------------
# m05 — 评测集管理：上传评测集 / 公共评测集库 / 维度 / 组合（BRD §8.22）
# ----------------------------------------------------------------------
class UploadedEvalSetRow(Base):
    """用户直接上传的 QA 评测集主记录（BRD FR-DS-SRC-001/002）。"""

    __tablename__ = "uploaded_eval_set"

    set_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    template_type: Mapped[str] = mapped_column(String(16), nullable=False, default="single")
    source_file: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dimension: Mapped[str | None] = mapped_column(String(64), nullable=True)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    quality_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    total_cases: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class UploadedEvalCaseRow(Base):
    """上传评测集样本（单轮 q/a/evidence/dimension；多轮 session_id+turns[]）。"""

    __tablename__ = "uploaded_eval_case"

    case_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    set_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    q: Mapped[str] = mapped_column(Text, nullable=False)
    a: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    dimension: Mapped[str | None] = mapped_column(String(64), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    turns: Mapped[list | None] = mapped_column(JSON, nullable=True)
    key_turn: Mapped[int | None] = mapped_column(Integer, nullable=True)
    turn_type: Mapped[str | None] = mapped_column(String(32), nullable=True)  # memory/coherence
    depends_on_turns: Mapped[list | None] = mapped_column(JSON, nullable=True)
    no_evidence: Mapped[int] = mapped_column(Integer, default=0)
    quality: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PublicEvalSetRow(Base):
    """公共评测集库条目（组织方预置，版本化，用户只读）。"""

    __tablename__ = "public_eval_set"

    set_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False, default="v1.0.0")
    dimensions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="governance_passed")
    quality_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class PublicEvalCaseRow(Base):
    """公共评测集库样本（预置 QA 对）。"""

    __tablename__ = "public_eval_case"

    case_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    set_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    q: Mapped[str] = mapped_column(Text, nullable=False)
    a: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    dimension: Mapped[str | None] = mapped_column(String(64), nullable=True)
    no_evidence: Mapped[int] = mapped_column(Integer, default=0)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="governance_passed")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class EvalSetDimensionRow(Base):
    """评测维度可配置体系（BRD FR-DS-SRC-004，暂不写死示例维度）。"""

    __tablename__ = "eval_set_dimension"

    dimension_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    enabled: Mapped[int] = mapped_column(Integer, default=1)


class EvalSetCompositionRow(Base):
    """Agent 评测前组合：指定单个 / 勾选维度 / 多来源合并（FR-DS-SRC-005）。"""

    __tablename__ = "eval_set_composition"

    composition_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    items: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ----------------------------------------------------------------------
# m08 — Agent 评测（BRD §9）：运行 / 单题结果 / ErrorBook
# ----------------------------------------------------------------------
class EvaluationRunRow(Base):
    """一次批量评测运行（组合后的临时标准化评测集作为输入）。"""

    __tablename__ = "evaluation_run"

    run_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    composition_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    adapter: Mapped[str] = mapped_column(String(64), nullable=False)
    adapter_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    finished: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class EvaluationCaseResultRow(Base):
    """单题输出 + 分层评分 + 归因（检索 / 答案 / 拒答 / 耗时成本）。"""

    __tablename__ = "evaluation_case_result"

    result_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    case_uid: Mapped[str] = mapped_column(String(128), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    gold_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    difficulty: Mapped[str | None] = mapped_column(String(16), nullable=True)
    dimension: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="doc_generated")
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 多轮运行必须保存完整对话过程，用于归因（BRD FR-DS-SRC-002 / m08）
    turn_outputs: Mapped[list | None] = mapped_column(JSON, nullable=True)
    retrieved: Mapped[list | None] = mapped_column(JSON, nullable=True)
    scores: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    diagnosis: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ErrorBookItemRow(Base):
    """失败案例：根因（D1–D9）、优化建议、回归记录（FR-OPT-003）。"""

    __tablename__ = "error_book_item"

    item_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    case_uid: Mapped[str | None] = mapped_column(String(128), nullable=True)
    diagnosis: Mapped[str] = mapped_column(String(16), nullable=False)
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    optimization: Mapped[str | None] = mapped_column(Text, nullable=True)
    regression: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
