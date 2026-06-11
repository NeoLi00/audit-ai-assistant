from __future__ import annotations

import hashlib
import re
from uuid import uuid4

CHUNKER_VERSION = "structured-v1"
TABLE_TYPES = {"table", "excel", "spreadsheet", "sheet", "csv"}
TEXT_TYPES = {"paragraph", "text", "heading", "list", "ocr_correction"}


class Chunker:
    def __init__(self, max_chars: int = 900, overlap: int = 120) -> None:
        self.max_chars = max_chars
        self.overlap = min(overlap, max(0, max_chars // 2))

    def chunk_blocks(self, blocks: list[dict]) -> list[dict]:
        chunks: list[dict] = []
        pending: list[dict] = []

        for raw_block in blocks:
            block = self._normalize_block(raw_block)
            if not block["text"]:
                continue

            if block["chunk_type"] in TABLE_TYPES:
                chunks.extend(self._flush_text_blocks(pending))
                pending = []
                chunks.extend(self._chunks_from_group([block], self._serialize_table(block), "table"))
                continue

            if pending and not self._can_merge(pending, block):
                chunks.extend(self._flush_text_blocks(pending))
                pending = []
            pending.append(block)

            if self._group_text_length(pending) >= self.max_chars:
                chunks.extend(self._flush_text_blocks(pending))
                pending = []

        chunks.extend(self._flush_text_blocks(pending))
        self._link_chunks(chunks)
        return chunks

    def _normalize_block(self, block: dict) -> dict:
        block_type = str(block.get("block_type") or "paragraph").lower()
        chunk_type = "table" if block_type in TABLE_TYPES else block_type if block_type in TEXT_TYPES else "paragraph"
        return {
            "id": block.get("id"),
            "document_id": block.get("document_id"),
            "block_type": block_type,
            "chunk_type": chunk_type,
            "text": str(block.get("text") or "").strip(),
            "page_number": block.get("page_number"),
            "sheet_name": block.get("sheet_name"),
            "heading_path": block.get("heading_path"),
        }

    def _can_merge(self, pending: list[dict], block: dict) -> bool:
        first = pending[0]
        if any(
            first.get(key) != block.get(key)
            for key in ("document_id", "heading_path", "sheet_name", "page_number", "chunk_type")
        ):
            return False
        return self._group_text_length([*pending, block]) <= self.max_chars

    def _flush_text_blocks(self, blocks: list[dict]) -> list[dict]:
        if not blocks:
            return []
        text = "\n".join(block["text"] for block in blocks if block["text"]).strip()
        chunk_type = blocks[0].get("chunk_type") or "paragraph"
        return self._chunks_from_group(blocks, text, chunk_type)

    def _chunks_from_group(self, blocks: list[dict], text: str, chunk_type: str) -> list[dict]:
        text = normalize_extracted_text(text)
        pieces = self._split_text(text)
        parent_id = self._parent_id(blocks)
        result = []
        for piece in pieces:
            result.append(self._build_chunk(blocks, piece, chunk_type, parent_id))
        return result

    def _split_text(self, text: str) -> list[str]:
        text = text.strip()
        if len(text) <= self.max_chars:
            return [text] if text else []

        segments = [
            segment.strip()
            for segment in re.split(r"(?<=[。！？；;])\s*|(?<=[.!?])(?!\d)\s*|\n+", text)
            if segment.strip()
        ]
        pieces: list[str] = []
        current = ""
        for segment in segments:
            if len(segment) > self.max_chars:
                if current:
                    pieces.append(current.strip())
                    current = ""
                pieces.extend(self._hard_split(segment))
                continue
            candidate = f"{current}\n{segment}".strip() if current else segment
            if len(candidate) <= self.max_chars:
                current = candidate
            else:
                if current:
                    pieces.append(current.strip())
                current = self._with_overlap(pieces[-1], segment) if pieces else segment
                if len(current) > self.max_chars:
                    pieces.extend(self._hard_split(current))
                    current = ""
        if current:
            pieces.append(current.strip())
        return pieces or self._hard_split(text)

    def _hard_split(self, text: str) -> list[str]:
        pieces = []
        start = 0
        while start < len(text):
            end = min(len(text), start + self.max_chars)
            piece = text[start:end].strip()
            if piece:
                pieces.append(piece)
            if end >= len(text):
                break
            start = max(0, end - self.overlap)
        return pieces

    def _with_overlap(self, previous: str, current: str) -> str:
        if not previous or not self.overlap:
            return current
        return f"{previous[-self.overlap:]}\n{current}".strip()

    def _serialize_table(self, block: dict) -> str:
        context = []
        if block.get("sheet_name"):
            context.append(f"工作表: {block['sheet_name']}")
        if block.get("heading_path"):
            context.append(f"标题: {block['heading_path']}")
        if block.get("page_number") is not None:
            context.append(f"页码: {block['page_number']}")
        context.append(block["text"])
        return "\n".join(context).strip()

    def _build_chunk(self, blocks: list[dict], text: str, chunk_type: str, parent_id: str) -> dict:
        first = blocks[0]
        block_ids = [block["id"] for block in blocks if block.get("id")]
        token_count = estimate_token_count(text)
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        metadata = {
            "page_number": first.get("page_number"),
            "sheet_name": first.get("sheet_name"),
            "heading_path": first.get("heading_path"),
            "chunk_type": chunk_type,
            "token_count": token_count,
            "content_hash": content_hash,
            "chunker_version": CHUNKER_VERSION,
            "block_ids": block_ids,
            "parent_chunk_id": parent_id,
        }
        return {
            "id": str(uuid4()),
            "document_id": first.get("document_id"),
            "block_ids": block_ids,
            "text": text,
            "metadata": metadata,
            "parent_chunk_id": parent_id,
            "prev_chunk_id": None,
            "next_chunk_id": None,
            "chunk_type": chunk_type,
            "token_count": token_count,
            "content_hash": content_hash,
            "chunker_version": CHUNKER_VERSION,
        }

    def _parent_id(self, blocks: list[dict]) -> str:
        first = blocks[0]
        raw = "|".join(
            str(first.get(key) or "")
            for key in ("document_id", "heading_path", "sheet_name", "page_number", "chunk_type")
        )
        return f"parent-{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]}"

    def _group_text_length(self, blocks: list[dict]) -> int:
        if not blocks:
            return 0
        return sum(len(block["text"]) for block in blocks) + max(0, len(blocks) - 1)

    def _link_chunks(self, chunks: list[dict]) -> None:
        for index, chunk in enumerate(chunks):
            chunk["chunk_index"] = index
            previous_chunk = chunks[index - 1] if index > 0 else None
            next_chunk = chunks[index + 1] if index + 1 < len(chunks) else None
            if previous_chunk and previous_chunk.get("document_id") == chunk.get("document_id"):
                chunk["prev_chunk_id"] = previous_chunk["id"]
                chunk["metadata"]["prev_chunk_id"] = previous_chunk["id"]
            else:
                chunk["metadata"]["prev_chunk_id"] = None
            if next_chunk and next_chunk.get("document_id") == chunk.get("document_id"):
                chunk["next_chunk_id"] = next_chunk["id"]
                chunk["metadata"]["next_chunk_id"] = next_chunk["id"]
            else:
                chunk["metadata"]["next_chunk_id"] = None


def estimate_token_count(text: str) -> int:
    cjk_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin_tokens = len(re.findall(r"[A-Za-z0-9_]+", text))
    punctuation = len(re.findall(r"[^\w\s\u4e00-\u9fff]", text))
    return cjk_chars + latin_tokens + max(0, punctuation // 4)


def normalize_extracted_text(text: str) -> str:
    """Clean common PDF table/OCR artifacts without changing ordinary prose."""
    text = re.sub(r"(?<=\d)\.\s*\n\s*(?=\d)", ".", text)
    text = re.sub(r"(?<=\d)\.\s*\|\s*(?=\d)", ".", text)
    text = re.sub(r"UEF[1Il|]\s*2\.\s*0", "UEFI2.0", text)
    text = re.sub(r"UEF[1Il|](?=\s*(?:模式|是|为|或|2))", "UEFI", text)
    return text
