from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models import Document, DocumentChunk, KnowledgeBase, User
from app.services.indexing.keyword_indexer import keyword_search
from app.services.indexing.vector_indexer import vector_indexer
from app.services.model_gateway.gateway import get_embedding_client
from app.services.permissions.permission_service import visible_kb_filter
from app.services.rag.fusion import reciprocal_rank_fusion


async def retrieve_evidence(
    db: Session,
    question: str,
    kb_id: str | None = None,
    kb_ids: list[str] | None = None,
    document_ids: list[str] | None = None,
    top_k: int = 8,
    current_user: User | None = None,
) -> list[dict]:
    result = await retrieve_evidence_with_trace(
        db,
        question,
        kb_id=kb_id,
        kb_ids=kb_ids,
        document_ids=document_ids,
        top_k=top_k,
        current_user=current_user,
    )
    return result["evidence"]


async def retrieve_evidence_with_trace(
    db: Session,
    question: str,
    kb_id: str | None = None,
    kb_ids: list[str] | None = None,
    document_ids: list[str] | None = None,
    top_k: int = 8,
    current_user: User | None = None,
) -> dict:
    allowed_kb_ids = _allowed_kb_ids(db, current_user, kb_id, kb_ids)
    requested_document_ids = None if document_ids is None else _unique_strings(document_ids)
    trace: dict = {
        "filters": {
            "kb_id": kb_id,
            "kb_ids": kb_ids or [],
            "document_ids": requested_document_ids or [],
            "allowed_kb_ids": allowed_kb_ids,
        },
        "vector": [],
        "keyword": [],
        "fused": [],
        "errors": {},
    }
    if allowed_kb_ids == []:
        return {"query": question, "evidence": [], "trace": trace}

    vector_results = []
    try:
        query_vector = (await get_embedding_client().embed_texts([question]))[0]
        vector_results = vector_indexer.search(
            query_vector,
            db=db,
            top_k=50,
            kb_id=kb_id,
            document_ids=requested_document_ids,
            current_user=current_user,
            allowed_kb_ids=allowed_kb_ids,
        )
    except Exception as exc:
        trace["errors"]["vector"] = str(exc)

    keyword_results = keyword_search(
        db,
        question,
        kb_id=kb_id,
        document_ids=requested_document_ids,
        current_user=current_user,
        allowed_kb_ids=allowed_kb_ids,
        top_k=50,
    )
    fused = reciprocal_rank_fusion([vector_results, keyword_results])
    evidence = _hydrate_evidence(db, fused, top_k)

    trace["vector"] = _trace_items(vector_results)
    trace["keyword"] = _trace_items(keyword_results)
    trace["fused"] = _trace_items(fused)
    return {"query": question, "evidence": evidence, "trace": trace}


def _allowed_kb_ids(
    db: Session,
    current_user: User | None,
    kb_id: str | None,
    kb_ids: list[str] | None,
) -> list[str] | None:
    requested_ids = [item for item in [*(kb_ids or []), *([kb_id] if kb_id else [])] if item]
    if requested_ids:
        unique_ids = list(dict.fromkeys(requested_ids))
        if current_user:
            visible_ids = []
            for requested_id in unique_ids:
                kb = db.get(KnowledgeBase, requested_id)
                if kb and visible_kb_filter(current_user, kb):
                    visible_ids.append(requested_id)
            return visible_ids
        return unique_ids
    if not current_user:
        return None
    query = db.query(KnowledgeBase.id)
    if current_user.role != "system_admin":
        query = query.filter(
            or_(
                KnowledgeBase.visibility == "shared",
                (KnowledgeBase.visibility == "private") & (KnowledgeBase.created_by == current_user.id),
            )
        )
    return [item[0] for item in query.all()]


def _unique_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def _hydrate_evidence(db: Session, fused: list[dict], top_k: int) -> list[dict]:
    chunk_ids = [item["chunk_id"] for item in fused]
    if not chunk_ids:
        return []
    chunks = {
        chunk.id: chunk
        for chunk in db.query(DocumentChunk).filter(DocumentChunk.id.in_(chunk_ids)).all()
    }
    docs = {
        doc.id: doc
        for doc in db.query(Document)
        .filter(Document.id.in_([chunk.document_id for chunk in chunks.values()]))
        .all()
    }
    evidence = []
    seen_contexts = set()
    for item in fused:
        chunk = chunks.get(item["chunk_id"])
        if not chunk:
            continue
        context_key = chunk.parent_chunk_id or chunk.id
        if context_key in seen_contexts:
            continue
        seen_contexts.add(context_key)
        doc = docs.get(chunk.document_id)
        metadata = chunk.metadata_json or {}
        evidence.append(
            {
                **item,
                "document_id": chunk.document_id,
                "kb_id": chunk.kb_id or (doc.kb_id if doc else None),
                "file_name": doc.file_name if doc else "",
                "text": chunk.text,
                "context_text": _expanded_context(db, chunk),
                "page_number": metadata.get("page_number"),
                "sheet_name": metadata.get("sheet_name"),
                "heading_path": metadata.get("heading_path"),
                "chunk_type": chunk.chunk_type or metadata.get("chunk_type"),
                "parent_chunk_id": chunk.parent_chunk_id,
                "prev_chunk_id": chunk.prev_chunk_id,
                "next_chunk_id": chunk.next_chunk_id,
            }
        )
        if len(evidence) >= top_k:
            break
    return evidence


def _expanded_context(db: Session, chunk: DocumentChunk, max_chars: int = 2400) -> str:
    ids = [item for item in [chunk.prev_chunk_id, chunk.id, chunk.next_chunk_id] if item]
    rows = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == chunk.document_id, DocumentChunk.id.in_(ids))
        .order_by(DocumentChunk.chunk_index)
        .all()
    )
    if not rows:
        return chunk.text
    parts = []
    for row in rows:
        parts.append(row.text)
        if sum(len(part) for part in parts) >= max_chars:
            break
    return "\n\n".join(parts)[:max_chars]


def _trace_items(items: list[dict]) -> list[dict]:
    return [
        {
            "chunk_id": item.get("chunk_id"),
            "document_id": item.get("document_id"),
            "score": item.get("score"),
            "rrf_score": item.get("rrf_score"),
            "source": item.get("source"),
        }
        for item in items[:50]
    ]
