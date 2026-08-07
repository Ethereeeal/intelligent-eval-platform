from __future__ import annotations

from dataclasses import dataclass

from modules.shared.core.config import settings


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
        # 返回绝对路径：解析器按路径打开文件，相对路径在容器工作目录变动时会找不到
        return StorageResult(object_path=str(target_path.resolve()), etag=f"size-{len(content)}")
