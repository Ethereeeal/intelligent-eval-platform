from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings


@dataclass
class StorageResult:
    object_path: str
    etag: str


class StorageService:
    def save_raw_document(self, file_name: str, content: bytes) -> StorageResult:
        target_dir = settings.raw_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / file_name
        target_path.write_bytes(content)
        return StorageResult(object_path=str(target_path), etag=f"size-{len(content)}")
