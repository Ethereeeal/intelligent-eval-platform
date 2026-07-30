from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.database import DatabaseService


class ExportService:
    def __init__(self) -> None:
        self.database = DatabaseService()

    def export_corpus(self, corpus_id: int, format: str = "jsonl") -> str:
        cases = self.database.list_eval_cases(corpus_id=corpus_id)
        if format == "jsonl":
            target = settings.storage_root / f"corpus_{corpus_id}_export.jsonl"
            with target.open("w", encoding="utf-8") as handle:
                for case in cases:
                    handle.write(json.dumps(case, ensure_ascii=False) + "\n")
            return str(target)
        if format == "json":
            target = settings.storage_root / f"corpus_{corpus_id}_export.json"
            grouped = self._group_by_document(cases)
            target.write_text(json.dumps(grouped, ensure_ascii=False, indent=2), encoding="utf-8")
            return str(target)
        raise ValueError("不支持的导出格式")

    def _group_by_document(self, cases: list[dict[str, Any]]) -> dict[str, Any]:
        documents = {}
        for case in cases:
            doc_id = case.get("document_id", 0)
            documents.setdefault(str(doc_id), []).append(case)
        return {"corpus_id": cases[0]["corpus_id"] if cases else None, "documents": documents, "exported_at": datetime.utcnow().isoformat()}
