from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Boolean, Float, JSON, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


class CorpusRow(Base):
    __tablename__ = "corpus"

    corpus_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    domain: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DocumentRow(Base):
    __tablename__ = "document"

    document_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    corpus_id: Mapped[int] = mapped_column(Integer, nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(64), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
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


class EiuRow(Base):
    __tablename__ = "eiu"

    eiu_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(Integer, nullable=False)
    corpus_id: Mapped[int] = mapped_column(Integer, nullable=False)
    block_id: Mapped[int] = mapped_column(Integer, nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    eiu_type: Mapped[str] = mapped_column(String(64), nullable=False)
    content_priority: Mapped[str] = mapped_column(String(8), nullable=False)
    weight: Mapped[int] = mapped_column(Integer, nullable=False)
    constraints_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    evidence_blocks: Mapped[list | None] = mapped_column(JSON, nullable=True)
    is_questionable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    exclusion_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    extraction_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    extraction_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="candidate")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class EvalCaseRow(Base):
    __tablename__ = "eval_case"

    case_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    intent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    eiu_id: Mapped[int] = mapped_column(Integer, nullable=False)
    corpus_id: Mapped[int] = mapped_column(Integer, nullable=False)
    document_id: Mapped[int] = mapped_column(Integer, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[str] = mapped_column(String(64), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(64), nullable=False)
    gold_answer: Mapped[str] = mapped_column(Text, nullable=False)
    must_have_points: Mapped[list | None] = mapped_column(JSON, nullable=True)
    acceptable_answers: Mapped[list | None] = mapped_column(JSON, nullable=True)
    evidence: Mapped[list | None] = mapped_column(JSON, nullable=True)
    content_priority: Mapped[str] = mapped_column(String(8), nullable=False)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="candidate")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class QualityCheckRow(Base):
    __tablename__ = "quality_check_result"

    check_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(Integer, nullable=False)
    passed: Mapped[bool] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@dataclass
class DatabaseResult:
    document_id: int
    block_ids: list[int]


class DatabaseService:
    def create_all(self) -> None:
        Base.metadata.create_all(bind=engine)

    def save_document(self, *, corpus_id: int, file_name: str, file_type: str, file_hash: str, storage_path: str) -> int:
        with SessionLocal() as session:
            row = DocumentRow(
                corpus_id=corpus_id,
                file_name=file_name,
                file_type=file_type,
                file_hash=file_hash,
                storage_path=storage_path,
                status="uploaded",
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row.document_id

    def find_by_hash(self, file_hash: str) -> int | None:
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

    def list_blocks_for_document(self, document_id: int) -> list[dict]:
        with SessionLocal() as session:
            rows = (
                session.query(BlockRow, DocumentRow)
                .join(DocumentRow, BlockRow.document_id == DocumentRow.document_id)
                .filter(BlockRow.document_id == document_id)
                .all()
            )
            return [
                {
                    "block_id": block.block_id,
                    "document_id": block.document_id,
                    "section_path": block.section_path,
                    "block_type": block.block_type,
                    "block_text": block.block_text,
                    "embedding_vector": block.embedding_vector,
                    "corpus_id": document.corpus_id,
                }
                for block, document in rows
            ]

    def save_corpus(self, *, name: str, description: str | None = None, domain: str | None = None) -> int:
        with SessionLocal() as session:
            row = CorpusRow(name=name, description=description, domain=domain)
            session.add(row)
            session.commit()
            session.refresh(row)
            return row.corpus_id

    def list_corpora(self) -> list[dict]:
        with SessionLocal() as session:
            rows = session.query(CorpusRow).all()
            return [
                {
                    "corpus_id": row.corpus_id,
                    "name": row.name,
                    "description": row.description,
                    "domain": row.domain,
                    "created_at": row.created_at.isoformat(),
                }
                for row in rows
            ]

    def get_document(self, document_id: int) -> dict | None:
        with SessionLocal() as session:
            row = session.query(DocumentRow).filter(DocumentRow.document_id == document_id).first()
            if row is None:
                return None
            return {
                "document_id": row.document_id,
                "corpus_id": row.corpus_id,
                "file_name": row.file_name,
                "file_type": row.file_type,
                "file_hash": row.file_hash,
                "storage_path": row.storage_path,
                "status": row.status,
                "created_at": row.created_at.isoformat(),
            }

    def save_eiu(
        self,
        *,
        document_id: int,
        corpus_id: int,
        block_id: int,
        statement: str,
        eiu_type: str,
        content_priority: str,
        weight: int,
        constraints_json: dict | None,
        evidence_blocks: list | None,
        is_questionable: bool,
        exclusion_reason: str | None,
        extraction_model: str | None,
        extraction_confidence: float | None,
    ) -> dict:
        with SessionLocal() as session:
            row = EiuRow(
                document_id=document_id,
                corpus_id=corpus_id,
                block_id=block_id,
                statement=statement,
                eiu_type=eiu_type,
                content_priority=content_priority,
                weight=weight,
                constraints_json=constraints_json,
                evidence_blocks=evidence_blocks,
                is_questionable=1 if is_questionable else 0,
                exclusion_reason=exclusion_reason,
                extraction_model=extraction_model,
                extraction_confidence=int(extraction_confidence) if extraction_confidence is not None else None,
                review_status="candidate",
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return {
                "eiu_id": row.eiu_id,
                "document_id": row.document_id,
                "corpus_id": row.corpus_id,
                "block_id": row.block_id,
                "statement": row.statement,
                "eiu_type": row.eiu_type,
                "content_priority": row.content_priority,
                "weight": row.weight,
                "constraints_json": row.constraints_json,
                "evidence_blocks": row.evidence_blocks,
                "is_questionable": bool(row.is_questionable),
                "exclusion_reason": row.exclusion_reason,
                "extraction_model": row.extraction_model,
                "extraction_confidence": row.extraction_confidence,
                "review_status": row.review_status,
            }

    def list_eius(self, corpus_id: int) -> list[dict]:
        with SessionLocal() as session:
            rows = session.query(EiuRow).filter(EiuRow.corpus_id == corpus_id).all()
            return [
                {
                    "eiu_id": row.eiu_id,
                    "document_id": row.document_id,
                    "corpus_id": row.corpus_id,
                    "block_id": row.block_id,
                    "statement": row.statement,
                    "eiu_type": row.eiu_type,
                    "content_priority": row.content_priority,
                    "weight": row.weight,
                    "constraints_json": row.constraints_json,
                    "evidence_blocks": row.evidence_blocks,
                    "is_questionable": bool(row.is_questionable),
                    "exclusion_reason": row.exclusion_reason,
                    "extraction_model": row.extraction_model,
                    "extraction_confidence": row.extraction_confidence,
                    "review_status": row.review_status,
                }
                for row in rows
            ]

    def save_eval_case(
        self,
        *,
        eiu_id: int,
        intent_id: str,
        question: str,
        question_type: str,
        difficulty: str,
        scope_type: str,
        gold_answer: str,
        must_have_points: list | None,
        acceptable_answers: list | None,
        evidence: list | None,
        content_priority: str,
        review_status: str,
    ) -> dict:
        with SessionLocal() as session:
            eiu = session.query(EiuRow).filter(EiuRow.eiu_id == eiu_id).first()
            if eiu is None:
                raise ValueError("EIU 不存在")
            row = EvalCaseRow(
                intent_id=intent_id,
                eiu_id=eiu_id,
                corpus_id=eiu.corpus_id,
                document_id=eiu.document_id,
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
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return {
                "case_id": row.case_id,
                "intent_id": row.intent_id,
                "eiu_id": row.eiu_id,
                "corpus_id": row.corpus_id,
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
                "review_status": row.review_status,
            }

    def list_eval_cases(self, corpus_id: int) -> list[dict]:
        with SessionLocal() as session:
            rows = session.query(EvalCaseRow).filter(EvalCaseRow.corpus_id == corpus_id).all()
            return [
                {
                    "case_id": row.case_id,
                    "intent_id": row.intent_id,
                    "eiu_id": row.eiu_id,
                    "corpus_id": row.corpus_id,
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
                    "review_status": row.review_status,
                }
                for row in rows
            ]

    def save_quality_check_result(self, case_id: int, passed: bool, reason: str) -> None:
        with SessionLocal() as session:
            row = QualityCheckRow(case_id=case_id, passed=1 if passed else 0, reason=reason)
            session.add(row)
            session.commit()

    def update_eval_case_status(self, case_id: int, status: str) -> None:
        with SessionLocal() as session:
            row = session.query(EvalCaseRow).filter(EvalCaseRow.case_id == case_id).first()
            if row is None:
                raise ValueError("评测样本不存在")
            row.review_status = status
            session.commit()
