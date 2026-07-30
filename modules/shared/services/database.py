from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import BigInteger, JSON, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from modules.shared.core.config import settings


class Base(DeclarativeBase):
    pass


class DocumentRow(Base):
    __tablename__ = "document"

    document_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    corpus_id: Mapped[int] = mapped_column(Integer, nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    file_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    minio_path: Mapped[str] = mapped_column(String(512), nullable=False)
    upload_user: Mapped[str | None] = mapped_column(String(128), nullable=True)
    document_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    authority_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    parse_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="uploaded")
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


class DocUpdateJobRow(Base):
    __tablename__ = "doc_update_job"

    job_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    corpus_id: Mapped[int] = mapped_column(Integer, nullable=False)
    document_id: Mapped[int] = mapped_column(Integer, nullable=False)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    phase: Mapped[str | None] = mapped_column(String(64), nullable=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CorpusRow(Base):
    __tablename__ = "corpus"

    corpus_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    domain: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    version: Mapped[str | None] = mapped_column(String(64), nullable=True)


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
    corpus_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
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


engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@dataclass
class DatabaseResult:
    document_id: int
    block_ids: list[int]


class DatabaseService:
    def create_all(self) -> None:
        Base.metadata.create_all(bind=engine)

    def save_document(
        self,
        *,
        corpus_id: int,
        file_name: str,
        file_type: str,
        file_hash: str,
        minio_path: str,
        file_size: int | None = None,
        upload_user: str | None = None,
        document_version: str | None = None,
        parse_status: str | None = None,
    ) -> int:
        with SessionLocal() as session:
            row = DocumentRow(
                corpus_id=corpus_id,
                file_name=file_name,
                file_type=file_type,
                file_size=file_size,
                file_hash=file_hash,
                minio_path=minio_path,
                upload_user=upload_user,
                document_version=document_version,
                parse_status=parse_status,
                status="uploaded",
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row.document_id

    def find_by_hash(self, file_hash: str) -> int | None:
        """Return existing document_id for the given hash, or None."""
        with SessionLocal() as session:
            row = session.query(DocumentRow).filter(DocumentRow.file_hash == file_hash).first()
            return row.document_id if row else None

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

    def list_blocks(self, corpus_id: int | None = None) -> list[dict]:
        with SessionLocal() as session:
            query = session.query(BlockRow, DocumentRow).join(DocumentRow, BlockRow.document_id == DocumentRow.document_id)
            if corpus_id is not None:
                query = query.filter(DocumentRow.corpus_id == corpus_id)
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
    # corpus
    # ------------------------------------------------------------------
    def save_corpus(self, *, name: str, description: str | None = None, domain: str | None = None, created_by: str | None = None) -> int:
        with SessionLocal() as session:
            row = CorpusRow(name=name, description=description, domain=domain, created_by=created_by)
            session.add(row)
            session.commit()
            session.refresh(row)
            return row.corpus_id

    def list_corpora(self) -> list[dict]:
        with SessionLocal() as session:
            rows = session.query(CorpusRow).order_by(CorpusRow.corpus_id.desc()).all()
            return [
                {
                    "corpus_id": row.corpus_id,
                    "name": row.name,
                    "description": row.description,
                    "domain": row.domain,
                    "created_by": row.created_by,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "version": row.version,
                }
                for row in rows
            ]

    def get_corpus(self, corpus_id: int) -> dict | None:
        with SessionLocal() as session:
            row = session.get(CorpusRow, corpus_id)
            if not row:
                return None
            return {
                "corpus_id": row.corpus_id,
                "name": row.name,
                "description": row.description,
                "domain": row.domain,
                "created_by": row.created_by,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "version": row.version,
            }

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
                "corpus_id": row.corpus_id,
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
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }

    def find_document_by_id(self, document_id: int) -> int | None:
        with SessionLocal() as session:
            row = session.get(DocumentRow, document_id)
            return row.document_id if row else None

    def list_documents(self, corpus_id: int | None = None) -> list[dict]:
        with SessionLocal() as session:
            query = session.query(DocumentRow)
            if corpus_id is not None:
                query = query.filter(DocumentRow.corpus_id == corpus_id)
            rows = query.order_by(DocumentRow.document_id.desc()).all()
            return [
                {
                    "document_id": row.document_id,
                    "corpus_id": row.corpus_id,
                    "file_name": row.file_name,
                    "file_type": row.file_type,
                    "file_size": row.file_size,
                    "parse_status": row.parse_status,
                    "status": row.status,
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
            session.commit()

    def delete_document_blocks(self, document_id: int) -> None:
        with SessionLocal() as session:
            session.query(BlockRow).filter(BlockRow.document_id == document_id).delete()
            session.commit()

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
    def save_job(self, *, corpus_id: int, document_id: int, job_type: str) -> int:
        with SessionLocal() as session:
            row = DocUpdateJobRow(
                corpus_id=corpus_id,
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
                "corpus_id": row.corpus_id,
                "document_id": row.document_id,
                "job_type": row.job_type,
                "status": row.status,
                "phase": row.phase,
                "progress": row.progress,
                "message": row.message,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            }
