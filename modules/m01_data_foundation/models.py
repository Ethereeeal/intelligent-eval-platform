from dataclasses import dataclass


@dataclass
class DocumentRecord:
    document_id: int
    corpus_id: int
    file_name: str
    file_type: str
    file_hash: str
    status: str
