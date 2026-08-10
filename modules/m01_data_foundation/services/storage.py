from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from modules.shared.core.config import settings


@dataclass
class StorageResult:
    object_path: str
    etag: str


class StorageService:
    def save_raw_document(self, file_name: str, content: bytes) -> StorageResult:
        target_dir = settings.raw_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        # 加唯一前缀避免同名文件互相覆盖落盘内容（同名不同内容多次上传会破坏彼此）
        safe_name = Path(file_name).name
        target_path = target_dir / f"{uuid.uuid4().hex[:12]}_{safe_name}"
        target_path.write_bytes(content)
        # 返回绝对路径：解析器按路径打开文件，相对路径在容器工作目录变动时会找不到
        return StorageResult(object_path=str(target_path.resolve()), etag=f"size-{len(content)}")

    def delete_raw_document(self, object_path: str | None) -> None:
        """物理删除落盘的原始文件（覆盖重算后清理旧文档用）。"""
        if not object_path:
            return
        path = Path(object_path)
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass
