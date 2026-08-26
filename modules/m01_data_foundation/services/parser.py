from __future__ import annotations

import csv
import io
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path

from modules.shared.core.config import settings


@dataclass
class ParsedBlock:
    section_path: str
    block_type: str
    block_text: str
    parent_index: int | None = None
    page_no: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    metadata_json: dict = field(default_factory=dict)


class DocumentParser:
    """层级文段解析器（README FR-PARSE-002 / FR-PARSE-003）。

    将文档解析为带结构层级的小文段：标题自动推断层级、构建 section_path、
    记录 parent_index（指向所属标题在结果列表中的位置，落库时再解析为 block_id），
    PDF 额外记录 page_no，所有块保留 start/end_offset 与 metadata 便于原文定位。
    """

    # 相邻同类型非标题块合并的字符上限，超过则另起一块，避免整篇合成超大块
    MAX_MERGE_CHARS = 1200

    def parse_document(self, file_path: Path, file_type: str) -> list[ParsedBlock]:
        suffix = file_type.lower() if file_type else file_path.suffix.lower()
        if suffix in {".pdf"}:
            raw = self._read_pdf(file_path)
        elif suffix in {".docx", ".doc"}:
            raw = self._read_docx(file_path)
        elif suffix in {".xlsx", ".xls", ".csv"}:
            # 表格类文件（excel/csv）：每行一条独立 Block，不合并、不逐句切分
            return self._read_tabular(file_path, suffix)
        else:
            raw = self._read_text(file_path)
        raw = self._merge_consecutive(raw)
        return self._assign_hierarchy(raw)

    # ------------------------------------------------------------------
    # 表格类文件（xlsx / csv）：每个数据行生成一个独立 Block
    # ------------------------------------------------------------------
    def _read_tabular(self, file_path: Path, suffix: str) -> list[ParsedBlock]:
        """表格类文件专用读取：每行一个 block（block_type="excel_row"）。

        excel/csv 只是普通支持的文件类型，分块方式为「每行一块」：
          - 每行独立 block，不做相邻合并（避免多行合成一大块）
          - EIU 抽取不特殊化，与普通文档同流程：一行可抽 0..n 条
          - 第一行非空且含文本时视为表头（列名），行文本拼成「列名: 值」
          - 表头含「问题/question」列时，该列值记入 metadata（生成时可复用）
          - 表头含「答案/answer」列时，该列值记入 metadata（生成时可复用标准答案）
        """
        rows: list[list[str]] = []
        sheet_name = "表格"
        if suffix == ".csv":
            text = self._safe_read(file_path)
            reader = csv.reader(io.StringIO(text))
            rows = [[cell.strip() for cell in row] for row in reader]
        else:
            import openpyxl

            wb = openpyxl.load_workbook(str(file_path), read_only=True, data_only=True)
            ws = wb.active
            sheet_name = ws.title or "表格"
            # 防压缩炸弹：限制活动工作表的行数 / 单元格数，超限直接拒绝
            max_row = ws.max_row or 0
            max_col = ws.max_column or 0
            if max_row > settings.max_table_rows:
                raise ValueError(
                    f"表格行数 {max_row} 超过上限 {settings.max_table_rows}，已拒绝解析"
                )
            if max_row * max_col > settings.max_xlsx_cells:
                raise ValueError(
                    f"表格单元格数 {max_row * max_col} 超过上限 {settings.max_xlsx_cells}，已拒绝解析"
                )
            for row in ws.iter_rows(values_only=True):
                rows.append([("" if c is None else str(c)).strip() for c in row])
        if len(rows) > settings.max_table_rows:
            raise ValueError(f"表格行数 {len(rows)} 超过上限 {settings.max_table_rows}，已拒绝解析")
        # 去掉全空行
        rows = [r for r in rows if any(r)]
        if not rows:
            return []
        # 表头识别：第一行是「列名」而非数据行时才视为表头。
        # 判定规则：非空、非纯数字行、且每个单元格都是短文本（≤30 字符）且不含数字
        # —— 数据行（如「甲类账户日累计限额1万元」）含数字或较长，不会被误判为表头。
        header = rows[0]
        non_empty_header = [c for c in header if c]
        has_header = bool(non_empty_header) and not all(
            c.replace(".", "").replace("-", "").isdigit() for c in non_empty_header
        ) and all(
            len(c) <= 30 and not any(ch.isdigit() for ch in c) for c in non_empty_header
        )
        if has_header:
            rows = rows[1:]
        blocks: list[ParsedBlock] = []
        for idx, row in enumerate(rows, start=1):
            if not any(row):
                continue
            parts: list[str] = []
            meta: dict = {
                "row": idx + (1 if has_header else 0),
                "sheet": sheet_name,
                "header": header if has_header else [],
            }
            for col_idx, cell in enumerate(row):
                name = (
                    header[col_idx]
                    if has_header and col_idx < len(header) and header[col_idx]
                    else f"列{col_idx + 1}"
                )
                parts.append(f"{name}: {cell}" if has_header else cell)
                low = name.lower()
                if "问题" in low or "question" in low:
                    meta["question"] = cell
                if "答案" in low or "answer" in low:
                    meta["answer"] = cell
            text = " | ".join(parts)
            if not text:
                continue
            blocks.append(
                ParsedBlock(
                    section_path=sheet_name,
                    block_type="excel_row",
                    block_text=text,
                    metadata_json=meta,
                )
            )
        return blocks

    # ------------------------------------------------------------------
    # 各格式读取：产出扁平 raw 列表，每项含 text / level / block_type 等
    # ------------------------------------------------------------------
    def _read_text(self, file_path: Path) -> list[dict]:
        text = self._safe_read(file_path)
        return self._md_lines_to_raw(text)

    def _read_pdf(self, file_path: Path) -> list[dict]:
        import fitz

        doc = fitz.open(file_path)
        if doc.page_count > settings.max_pdf_pages:
            raise ValueError(
                f"PDF 页数 {doc.page_count} 超过上限 {settings.max_pdf_pages}，已拒绝解析"
            )
        raw: list[dict] = []
        for page_index in range(doc.page_count):
            page = doc.load_page(page_index)
            page_no = str(page_index + 1)
            blocks = page.get_text("dict").get("blocks", [])
            sizes = [
                span["size"]
                for b in blocks
                if b.get("type") == 0
                for line in b.get("lines", [])
                for span in line.get("spans", [])
            ]
            body_size = statistics.median(sizes) if sizes else 11.0
            for b in blocks:
                if b.get("type") != 0:
                    continue
                spans_texts: list[str] = []
                max_size = 0.0
                bold = False
                for line in b.get("lines", []):
                    for span in line.get("spans", []):
                        spans_texts.append(span["text"])
                        max_size = max(max_size, span["size"])
                        if span.get("flags", 0) & 16:  # bold
                            bold = True
                block_text = "".join(spans_texts).strip()
                if not block_text:
                    continue
                is_title = (max_size >= body_size * 1.2) or (bold and len(block_text) < 40)
                level = self._pdf_level(max_size, body_size) if is_title else None
                raw.append(
                    {
                        "text": block_text,
                        "level": level,
                        "block_type": "title" if is_title else "paragraph",
                        "page_no": page_no,
                        "metadata": {"font_size": round(max_size, 1)},
                    }
                )
        return raw

    def _read_docx(self, file_path: Path) -> list[dict]:
        import docx
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        document = docx.Document(str(file_path))
        table_cells = sum(len(table.rows) * len(table.columns) for table in document.tables)
        if len(document.paragraphs) + table_cells > settings.max_docx_blocks:
            raise ValueError(
                f"DOCX 元素数（段落+表格单元格）超过上限 {settings.max_docx_blocks}，已拒绝解析"
            )
        raw: list[dict] = []
        table_no = 0
        # document.paragraphs / document.tables 分开遍历会改变正文和表格的原始顺序。
        for child in document.element.body.iterchildren():
            if child.tag.endswith("}p"):
                self._append_docx_paragraph(raw, Paragraph(child, document))
            elif child.tag.endswith("}tbl"):
                table_no += 1
                self._append_docx_table(raw, Table(child, document), table_no)
        return raw

    def _append_docx_paragraph(self, raw: list[dict], para: object) -> None:
        """将 DOCX 段落转换为标题、条款项或普通段落，保留编号供上下文继承。"""
        text = str(getattr(para, "text", "") or "").strip()
        if not text:
            return
        style = getattr(para, "style", None)
        style_name = style.name if style else ""
        match = re.match(r"^Heading\s+(\d+)", style_name)
        if match:
            raw.append({"text": text, "level": int(match.group(1)), "block_type": "title"})
            return
        heading_level = self._docx_heading_level(text)
        if heading_level is not None:
            raw.append({"text": text, "level": heading_level, "block_type": "title", "metadata": self._structural_metadata(text)})
            return
        metadata = self._structural_metadata(text)
        if self._docx_has_numbering(para) and "item_no" not in metadata:
            metadata["item_no"] = "word-numbered"
        raw.append({"text": text, "level": None, "block_type": "list_item" if metadata.get("item_no") else "paragraph", "metadata": metadata})

    @staticmethod
    def _append_docx_table(raw: list[dict], table: object, table_no: int) -> None:
        """保留表格原始位置，并为行保留表头和合并单元格提示。"""
        rows: list[list[str]] = []
        for row in getattr(table, "rows", []):
            values: list[str] = []
            seen_cells: set[int] = set()
            for cell in row.cells:
                cell_id = id(cell._tc)
                if cell_id not in seen_cells:
                    seen_cells.add(cell_id)
                    values.append(cell.text.strip())
            if any(values):
                rows.append(values)
        if not rows:
            return
        headers = rows[0]
        for row_no, values in enumerate(rows, start=1):
            raw.append({
                "text": " | ".join(values),
                "level": None,
                "block_type": "table_header" if row_no == 1 else "table_row",
                "metadata": {"table_id": f"docx-table-{table_no}", "table_row": row_no, "headers": headers, "merged_cell_context": len(values) != len(headers)},
            })

    @staticmethod
    def _docx_has_numbering(para: object) -> bool:
        paragraph_xml = getattr(para, "_p", None)
        return bool(paragraph_xml is not None and paragraph_xml.pPr is not None and paragraph_xml.pPr.numPr is not None)

    @staticmethod
    def _structural_metadata(text: str) -> dict:
        metadata: dict = {}
        article = re.match(r"^第\s*([一二三四五六七八九十百千万零〇两0-9]+)\s*条", text)
        if article:
            metadata["article_no"] = f"第{article.group(1)}条"
        item = re.match(r"^\s*(（[一二三四五六七八九十百千万零〇两0-9]+）|[一二三四五六七八九十百千万零〇两0-9]+[、.]|\d+[.)])", text)
        if item:
            metadata["item_no"] = item.group(1)
        return metadata

    @staticmethod
    def _is_list_lead(text: str) -> bool:
        return bool(re.search(r"(?:包括|如下|下列|应当具备|满足以下|符合以下|有下列|按下列).{0,30}(?:条件|情形|要求|事项|资料|材料|方式)?[：:]?$", text))

            # 中文制度/规程类文档常未套用 Heading 样式，按常见章节/条款模式推断层级

    @staticmethod
    def _docx_heading_level(text: str) -> int | None:
        """按中文文档常见标题模式推断层级（章=1 / 节·部分=2 / 条=3 / 附件=2）。"""
        if re.match(r"^第[一二三四五六七八九十百千零两]+\s*章", text):
            return 1
        if re.match(r"^第[一二三四五六七八九十百千零两]+\s*[节部分]", text):
            return 2
        if re.match(r"^第[一二三四五六七八九十百千零两]+\s*条", text):
            return 3
        if re.match(r"^(附件|附录)\s*[0-9一二三四五六七八九十]*", text):
            return 2
        return None

    # ------------------------------------------------------------------
    # 层级构建
    # ------------------------------------------------------------------
    def _assign_hierarchy(self, raw: list[dict]) -> list[ParsedBlock]:
        blocks: list[ParsedBlock] = []
        # 栈保存 (在 blocks 中的位置, level)，栈顶为当前最近的标题
        stack: list[tuple[int, int]] = []
        current_article_no: str | None = None
        active_lead_index: int | None = None
        for item in raw:
            level = item.get("level")
            metadata = dict(item.get("metadata") or {})
            # 标题先出栈同级/更高级祖先，再计算其所属层级
            if level is not None:
                while stack and stack[-1][1] >= level:
                    stack.pop()
            ancestor_texts = [blocks[i].block_text for i, _ in stack]
            section_path = " / ".join(ancestor_texts) if ancestor_texts else "未分类"
            parent_index = stack[-1][0] if stack else None
            article_no = metadata.get("article_no")
            if article_no:
                current_article_no = str(article_no)
            elif current_article_no:
                metadata["article_no"] = current_article_no
            if metadata.get("item_no") and active_lead_index is not None:
                parent_index = active_lead_index
                metadata["lead_index"] = active_lead_index
            if metadata.get("article_no") or metadata.get("item_no"):
                metadata["list_path"] = "/".join(
                    str(part) for part in (metadata.get("article_no"), metadata.get("item_no")) if part
                )
            block = ParsedBlock(
                section_path=section_path,
                block_type=item.get("block_type", "paragraph"),
                block_text=item["text"],
                parent_index=parent_index,
                page_no=item.get("page_no"),
                start_offset=item.get("start"),
                end_offset=item.get("end"),
                metadata_json=metadata,
            )
            blocks.append(block)
            if level is not None:
                stack.append((len(blocks) - 1, level))
                active_lead_index = None
            elif self._is_list_lead(block.block_text):
                active_lead_index = len(blocks) - 1
            elif block.block_type not in {"list_item", "table_header", "table_row"}:
                active_lead_index = None
        return blocks

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------
    @staticmethod
    def _md_lines_to_raw(text: str) -> list[dict]:
        raw: list[dict] = []
        offset = 0
        for line in text.split("\n"):
            line_start = offset
            offset += len(line) + 1
            stripped = line.strip()
            if not stripped:
                continue
            match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
            if match:
                raw.append(
                    {
                        "text": match.group(2).strip(),
                        "level": len(match.group(1)),
                        "block_type": "title",
                        "start": line_start,
                        "end": line_start + len(line),
                    }
                )
            else:
                list_match = re.match(r"^([-*+]|\d+[.)])\s+", stripped)
                raw.append(
                    {
                        "text": stripped,
                        "level": None,
                        "block_type": "list_item" if list_match else "paragraph",
                        "start": line_start,
                        "end": line_start + len(line),
                    }
                )
        return raw

    @staticmethod
    def _merge_consecutive(raw: list[dict]) -> list[dict]:
        """合并相邻的非标题块（同类型），避免一行一段造成过碎；但受 MAX_MERGE_CHARS 限制。"""
        _SENTENCE_END = re.compile(r"[。！？；;….]{1,}$")
        merged: list[dict] = []
        for item in raw:
            if item.get("level") is not None:
                merged.append(item)
                continue
            if item.get("block_type") in {"list_item", "table_header", "table_row"}:
                merged.append(item)
                continue
            last = merged[-1] if merged else None
            if (
                last is None
                or last.get("level") is not None
                or last.get("block_type") != item.get("block_type")
            ):
                merged.append(item)
                continue
            merged_len = len(last["text"]) + len(item["text"])
            if merged_len > DocumentParser.MAX_MERGE_CHARS * 2:
                # 双上限保险：无论如何强制断，防止超大块
                merged.append(item)
            elif merged_len > DocumentParser.MAX_MERGE_CHARS and not _SENTENCE_END.search(
                last["text"]
            ):
                # 超长但上一块句子未结束：继续合并，等下一个句末再断（消除硬切腰斩）
                last["text"] = f"{last['text']}\n{item['text']}"
                last["end"] = item.get("end")
            elif merged_len > DocumentParser.MAX_MERGE_CHARS and _SENTENCE_END.search(
                last["text"]
            ):
                # 超长且上一块已是完整句：在句末软断点处断开
                merged.append(item)
            else:
                last["text"] = f"{last['text']}\n{item['text']}"
                last["end"] = item.get("end")
        return merged

    @staticmethod
    def _pdf_level(max_size: float, body_size: float) -> int:
        ratio = max_size / body_size if body_size else 1.0
        if ratio >= 1.6:
            return 1
        if ratio >= 1.3:
            return 2
        return 3

    @staticmethod
    def _safe_read(file_path: Path) -> str:
        for enc in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
            try:
                return Path(file_path).read_text(encoding=enc)
            except (UnicodeDecodeError, UnicodeError):
                continue
        return Path(file_path).read_text(encoding="utf-8", errors="replace")
