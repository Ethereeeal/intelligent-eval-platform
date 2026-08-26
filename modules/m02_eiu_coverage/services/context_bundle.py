"""条款级上下文拼装：Block 是证据定位单位，不是知识点边界。"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any


_ARTICLE_RE = re.compile(r"\u7b2c\s*([\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\u767e\u5343\u4e07\u96f6\u3007\u4e240-9]+)\s*\u6761")


class ContextBundleBuilder:
    """从同一文档的结构化 Block 构造受限、可追溯的 LLM 上下文。"""

    def __init__(self, blocks: list[dict[str, Any]]) -> None:
        self.blocks = list(blocks)
        self.by_id = {int(block["block_id"]): block for block in self.blocks}
        self.index_by_id = {int(block["block_id"]): index for index, block in enumerate(self.blocks)}
        self.children: dict[int, list[dict[str, Any]]] = defaultdict(list)
        self.article_blocks: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.tables: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for block in self.blocks:
            parent_id = block.get("parent_block_id")
            if parent_id:
                self.children[int(parent_id)].append(block)
            meta = self._meta(block)
            article_no = meta.get("article_no") or self._article_no(str(block.get("block_text") or ""))
            if article_no:
                self.article_blocks[str(article_no)].append(block)
            if meta.get("table_id"):
                self.tables[str(meta["table_id"])].append(block)

    def build_all(self) -> dict[int, dict[str, Any]]:
        return {int(block["block_id"]): self.build(block) for block in self.blocks}

    def build(self, block: dict[str, Any]) -> dict[str, Any]:
        index = self.index_by_id[int(block["block_id"])]
        meta = self._meta(block)
        source_roles: dict[int, set[str]] = defaultdict(set)

        def add(role: str, candidate: dict[str, Any] | None) -> str:
            if not candidate:
                return ""
            candidate_id = int(candidate["block_id"])
            source_roles[candidate_id].add(role)
            return str(candidate.get("block_text") or "")

        current = add("current", block)
        direct_parent = self._direct_parent(block)
        parent_text = add("parent", direct_parent)
        inherited_parent = self._nearest_parent(block)
        inherited_text = add("inherited", inherited_parent)
        lead = inherited_parent if inherited_parent and self._is_list_lead(inherited_parent) else None
        lead_text = add("lead", lead)

        previous = self.blocks[index - 1] if index > 0 else None
        following = self.blocks[index + 1] if index + 1 < len(self.blocks) else None
        prev_text = add("neighbor", previous)
        next_text = add("neighbor", following)

        article_no = meta.get("article_no") or self._article_no(current)
        article_members = self.article_blocks.get(str(article_no), []) if article_no else []
        siblings = [candidate for candidate in article_members if candidate is not block][:6]
        sibling_texts = [add("same_article", candidate) for candidate in siblings]
        # 条款批审只使用同一条款内的原始 Block；不会跨文档扩展证据范围。
        article_batch = [
            {
                "block_id": int(candidate["block_id"]),
                "text": str(candidate.get("block_text") or ""),
            }
            for candidate in article_members[:12]
        ]

        reference_texts: list[str] = []
        for referenced_article in self._references(current):
            for candidate in self.article_blocks.get(referenced_article, [])[:4]:
                reference_texts.append(add("reference", candidate))

        table_headers: list[str] = []
        table_id = meta.get("table_id")
        if table_id:
            for candidate in self.tables.get(str(table_id), []):
                if candidate.get("block_type") == "table_header":
                    table_headers.append(add("table_header", candidate))

        definition_texts: list[str] = []
        for candidate in self._definition_candidates(block)[:3]:
            definition_texts.append(add("definition", candidate))

        sources = [
            {"block_id": block_id, "roles": sorted(roles)}
            for block_id, roles in source_roles.items()
        ]

        return {
            "prev": prev_text,
            "next": next_text,
            "current": current,
            "parent": parent_text,
            "inherited": inherited_text,
            "lead": lead_text,
            "same_article": "\n".join(text for text in sibling_texts if text),
            "article_batch": article_batch,
            "references": "\n".join(text for text in reference_texts if text),
            "table_headers": "\n".join(text for text in table_headers if text),
            "definitions": "\n".join(text for text in definition_texts if text),
            "evidence_sources": sources,
            "evidence_catalog": ", ".join(
                f"{source['block_id']}[{'/'.join(source['roles'])}]" for source in sources
            ),
            "_resolver": self,
        }

    def expand(self, bundle: dict[str, Any], requests: list[dict[str, Any]]) -> dict[str, Any]:
        """按 LLM 声明的缺失语义扩展文档上下文映射，最多补入四个可追溯 Block。"""
        expanded = dict(bundle)
        source_roles: dict[int, set[str]] = defaultdict(set)
        for source in bundle.get("evidence_sources") or []:
            if not isinstance(source, dict) or source.get("block_id") is None:
                continue
            source_roles[int(source["block_id"])].update(source.get("roles") or [source.get("role") or "context"])
        resolved: list[dict[str, Any]] = []
        unresolved: list[dict[str, Any]] = []
        for request in requests[:3]:
            if not isinstance(request, dict):
                continue
            candidates = self._resolve_request(request)
            if not candidates:
                unresolved.append(request)
                continue
            kind = str(request.get("kind") or "context").strip().lower()
            role = f"requested_{kind}" if kind else "requested_context"
            for candidate in candidates:
                candidate_id = int(candidate["block_id"])
                source_roles[candidate_id].add(role)
                resolved.append({"block_id": candidate_id, "role": role, "text": str(candidate.get("block_text") or "")})
        sources = [
            {"block_id": block_id, "roles": sorted(roles)}
            for block_id, roles in source_roles.items()
        ]
        expanded["evidence_sources"] = sources
        expanded["evidence_catalog"] = ", ".join(
            f"{source['block_id']}[{'/'.join(source['roles'])}]" for source in sources
        )
        expanded["resolved_requests"] = resolved
        expanded["unresolved_requests"] = unresolved
        expanded["expanded_context"] = "\n".join(
            f"Block {item['block_id']} ({item['role']}): {item['text']}" for item in resolved
        )
        return expanded

    def _resolve_request(self, request: dict[str, Any]) -> list[dict[str, Any]]:
        article_no = str(request.get("article_no") or "").strip()
        if article_no and article_no in self.article_blocks:
            return self.article_blocks[article_no][:4]
        query = str(request.get("query") or "").strip()
        kind = str(request.get("kind") or "").strip().lower()
        query_terms = self._key_terms(query)
        ranked: list[tuple[int, int, dict[str, Any]]] = []
        for index, candidate in enumerate(self.blocks):
            text = str(candidate.get("block_text") or "")
            score = len(query_terms.intersection(self._key_terms(text)))
            if kind == "definition" and self._is_definition(candidate):
                score += 2
            if score:
                ranked.append((score, -index, candidate))
        ranked.sort(reverse=True, key=lambda item: (item[0], item[1]))
        return [candidate for _score, _index, candidate in ranked[:4]]

    def _direct_parent(self, block: dict[str, Any]) -> dict[str, Any] | None:
        parent_id = block.get("parent_block_id")
        return self.by_id.get(int(parent_id)) if parent_id else None

    def _nearest_parent(self, block: dict[str, Any]) -> dict[str, Any] | None:
        parent_id = block.get("parent_block_id")
        visited: set[int] = set()
        while parent_id and int(parent_id) not in visited:
            visited.add(int(parent_id))
            parent = self.by_id.get(int(parent_id))
            if not parent:
                return None
            if parent.get("block_type") != "title":
                return parent
            parent_id = parent.get("parent_block_id")
        return None

    def _definition_candidates(self, block: dict[str, Any]) -> list[dict[str, Any]]:
        current_text = str(block.get("block_text") or "")
        current_section = str(block.get("section_path") or "")
        terms = self._key_terms(current_text)
        candidates: list[dict[str, Any]] = []
        for candidate in self.blocks:
            if candidate is block or not self._is_definition(candidate):
                continue
            candidate_text = str(candidate.get("block_text") or "")
            same_section = current_section and candidate.get("section_path") == current_section
            if same_section or terms.intersection(self._key_terms(candidate_text)):
                candidates.append(candidate)
        return candidates

    @staticmethod
    def _is_definition(block: dict[str, Any]) -> bool:
        text = str(block.get("block_text") or "")
        return bool(re.search(r"\u662f\u6307|\u7cfb\u6307|\u4ee5\u4e0b\u7b80\u79f0|\u5b9a\u4e49\u5982\u4e0b", text))

    @staticmethod
    def _key_terms(text: str) -> set[str]:
        return {term for term in re.findall(r"[\u4e00-\u9fff]{2,8}", text) if len(term) >= 2}

    @staticmethod
    def _meta(block: dict[str, Any]) -> dict[str, Any]:
        value = block.get("metadata_json")
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _article_no(text: str) -> str | None:
        match = _ARTICLE_RE.search(text)
        return f"\u7b2c{match.group(1)}\u6761" if match else None

    @staticmethod
    def _references(text: str) -> list[str]:
        return [f"\u7b2c{value}\u6761" for value in _ARTICLE_RE.findall(text)]

    @staticmethod
    def _is_list_lead(block: dict[str, Any]) -> bool:
        text = str(block.get("block_text") or "")
        return bool(re.search(r"(?:\u5305\u62ec|\u5982\u4e0b|\u4e0b\u5217|\u5e94\u5f53\u5177\u5907|\u6ee1\u8db3\u4ee5\u4e0b|\u7b26\u5408\u4ee5\u4e0b|\u6709\u4e0b\u5217|\u6309\u4e0b\u5217).{0,30}(?:\u6761\u4ef6|\u60c5\u5f62|\u8981\u6c42|\u4e8b\u9879|\u8d44\u6599|\u6750\u6599|\u65b9\u5f0f)?[\uff1a:]?$", text))
