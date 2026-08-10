"""向 SQLite 演示库灌入模板示例数据（文档 / 知识点 EIU / 问答对）。

用法：
    cd intelligent-eval-platform
    DATABASE_URL=sqlite:///./storage/dev.db python3 modules/shared/scripts/seed_demo_data.py

数据来源：data/template/{documents,knowledge_points,qa_pairs}.json
- documents.json 的 document_id 与 knowledge_points / qa_pairs 的 document_id 一致（9/10/11/12/14/16/17）
- 每个文档按 kp 的 block_id/section_path 造 document_block 行，供 eiu JOIN
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from modules.shared.services.database import (  # noqa: E402
    Base,
    BlockRow,
    DocumentRow,
    EiuRow,
    GeneratedCaseRow,
)
from modules.shared.core.config import settings  # noqa: E402

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "data", "template")


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def load(name):
    with open(os.path.join(TEMPLATE_DIR, name), "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    database_url = os.environ.get("DATABASE_URL") or settings.database_url
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    documents = load("documents.json")
    kps = load("knowledge_points.json")
    qas = load("qa_pairs.json")

    with SessionLocal() as session:
        # 1) 文档
        doc_ids = set()
        for d in documents:
            doc_ids.add(d["document_id"])
            session.add(DocumentRow(
                document_id=d["document_id"],
                file_name=d["file_name"],
                file_type=d.get("file_type") or "docx",
                file_size=d.get("file_size"),
                file_hash=d.get("file_hash") or f"seed-{d['document_id']}",
                minio_path=d.get("minio_path") or f"seed/{d['file_name']}",
                folder_path=d.get("folder_path") or "",
                purpose=d.get("purpose") or "basic",
                parse_status=d.get("parse_status") or "parsed",
                status=d.get("status") or "uploaded",
                created_at=_now(),
            ))
        session.flush()

        # 2) 文档块 + EIU
        seen_blocks = set()
        for kp in kps:
            did = kp["document_id"]
            bid = kp["block_id"]
            if (did, bid) not in seen_blocks:
                seen_blocks.add((did, bid))
                session.add(BlockRow(
                    block_id=bid,
                    document_id=did,
                    section_path=kp.get("section_path") or "",
                    block_type="paragraph",
                    block_text=kp.get("statement") or "",
                ))
            session.add(EiuRow(
                eiu_id=kp["eiu_id"],
                block_id=bid,
                document_id=did,
                statement=kp["statement"],
                eiu_type=kp.get("eiu_type") or "rule",
                content_priority=kp.get("content_priority") or "P2",
                weight=kp.get("weight") or 1,
                constraints_json=kp.get("constraints"),
                evidence_blocks=kp.get("evidence_blocks") or [bid],
                is_questionable=bool(kp.get("is_questionable", True)),
                exclusion_reason=kp.get("exclusion_reason"),
                extraction_model=kp.get("extraction_model"),
                extraction_confidence=kp.get("extraction_confidence"),
                review_status=kp.get("review_status") or "candidate",
            ))
        session.flush()

        # 3) 问答对
        for qa in qas:
            session.add(GeneratedCaseRow(
                intent_id=qa.get("intent_id") or f"intent-{qa['case_id']}",
                eiu_id=qa.get("eiu_id"),
                document_id=qa.get("document_id"),
                question=qa["question"],
                question_type=qa.get("question_type") or "factual",
                difficulty=qa.get("difficulty") or "medium",
                scope_type=qa.get("scope_type") or "single",
                gold_answer=qa.get("gold_answer") or "",
                must_have_points=qa.get("must_have_points"),
                acceptable_answers=qa.get("acceptable_answers"),
                evidence=qa.get("evidence"),
                content_priority=qa.get("content_priority") or "P2",
                review_status=qa.get("review_status") or "candidate",
                review_tag=qa.get("review_tag"),
            ))
        session.commit()

    print(f"seeded: documents={len(documents)} kp(eiu)={len(kps)} qa(cases)={len(qas)}")


if __name__ == "__main__":
    main()
