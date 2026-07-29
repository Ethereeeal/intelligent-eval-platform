from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ParsedBlock:
    section_path: str
    block_text: str
    block_type: str = "paragraph"


class DocumentParser:
    def parse_file(self, file_path: Path) -> list[ParsedBlock]:
        raw_text = self._read_text(file_path)
        return self.split_text(raw_text)

    def split_text(self, raw_text: str) -> list[ParsedBlock]:
        normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n")
        paragraphs = [line.strip() for line in normalized.split("\n") if line.strip()]
        if not paragraphs:
            return []
        return [
            ParsedBlock(section_path=f"paragraph_{index + 1}", block_text=paragraph)
            for index, paragraph in enumerate(paragraphs)
        ]

    def _read_text(self, file_path: Path) -> str:
        if file_path.suffix.lower() in {".txt", ".md", ".csv", ".json", ".log"}:
            return file_path.read_text(encoding="utf-8", errors="ignore")
        return file_path.read_bytes().decode("utf-8", errors="ignore")
