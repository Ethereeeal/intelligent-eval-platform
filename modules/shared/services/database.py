from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text, create_engine
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
    file_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    minio_path: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="uploaded")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BlockRow(Base):
    __tablename__ = "document_block"

    block_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(Integer, nullable=False)
    section_path: Mapped[str] = mapped_column(String(512), nullable=False)
    block_type: Mapped[str] = mapped_column(String(64), nullable=False, default="paragraph")
    block_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_vector: Mapped[dict | None] = mapped_column(JSON, nullable=True)


engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@dataclass
class DatabaseResult:
    document_id: int
    block_ids: list[int]


class DatabaseService:
    def create_all(self) -> None:
        Base.metadata.create_all(bind=engine)

    def save_document(self, *, corpus_id: int, file_name: str, file_type: str, file_hash: str, minio_path: str) -> int:
        with SessionLocal() as session:
            row = DocumentRow(
                corpus_id=corpus_id,
                file_name=file_name,
                file_type=file_type,
                file_hash=file_hash,
                minio_path=minio_path,
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
        block_ids: list[int] = []
        with SessionLocal() as session:
            for block in blocks:
                row = BlockRow(
                    document_id=document_id,
                    section_path=block["section_path"],
                    block_type=block.get("block_type", "paragraph"),
                    block_text=block["block_text"],
                    embedding_vector=block.get("embedding_vector"),
                )
                session.add(row)
                session.flush()
                block_ids.append(row.block_id)
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
                    "section_path": block.section_path,
                    "block_type": block.block_type,
                    "block_text": block.block_text,
                    "embedding_vector": block.embedding_vector,
                }
                for block, _document in rows
            ]
