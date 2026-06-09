import hashlib
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.models import Document, DocumentBlock, DocumentChunk
from app.db.session import SessionLocal
from app.services.indexing.keyword_indexer import keyword_indexer
from app.services.indexing.vector_indexer import vector_indexer
from app.services.model_gateway.gateway import get_embedding_client
from app.services.parser.document_parser import DocumentParser
from app.services.rag.chunker import Chunker
from app.services.storage.minio_client import ObjectStorage
from app.services.tasks.celery_app import celery_app


@celery_app.task(name="process_document")
def process_document_task(document_id: str) -> dict:
    with SessionLocal() as db:
        return process_document(db, document_id)


def process_document_in_background(document_id: str) -> dict:
    with SessionLocal() as db:
        return process_document(db, document_id)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def process_document(db: Session, document_id: str) -> dict:
    import asyncio

    return asyncio.run(process_document_async(db, document_id))


async def process_document_async(db: Session, document_id: str) -> dict:
    document = db.get(Document, document_id)
    if not document:
        return {"status": "failed", "error": "document not found"}

    storage = ObjectStorage()
    path = storage.local_path_for(document.minio_object_key)
    document.status = "parsing"
    db.commit()

    parse_result = DocumentParser().parse(path)
    document.error_message = parse_result.error_message
    if parse_result.status == "failed":
        document.status = "failed"
        db.commit()
        return {"status": "failed", "error": parse_result.error_message}

    keyword_indexer.delete_document(db, document.id)
    vector_indexer.delete_document(document.id)
    db.query(DocumentBlock).filter(DocumentBlock.document_id == document.id).delete()
    db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete()
    db.flush()

    block_rows = []
    for block in parse_result.blocks:
        row = DocumentBlock(
            document_id=document.id,
            block_type=block.block_type,
            page_number=block.page_number,
            sheet_name=block.sheet_name,
            heading_path=block.heading_path,
            paragraph_index=block.paragraph_index,
            bbox_json=block.bbox_json,
            text=block.text,
            confidence=block.confidence,
        )
        db.add(row)
        block_rows.append(row)
    db.flush()

    document.status = "chunking"
    db.flush()
    chunk_inputs = [
        {
            "id": block.id,
            "document_id": block.document_id,
            "text": block.text,
            "page_number": block.page_number,
            "sheet_name": block.sheet_name,
            "heading_path": block.heading_path,
            "block_type": block.block_type,
        }
        for block in block_rows
    ]
    chunk_payloads = Chunker().chunk_blocks(chunk_inputs)
    chunk_rows = []
    for payload in chunk_payloads:
        row = DocumentChunk(
            document_id=document.id,
            kb_id=document.kb_id,
            block_ids=payload["block_ids"],
            chunk_index=payload["chunk_index"],
            parent_chunk_id=payload["parent_chunk_id"],
            prev_chunk_id=payload["prev_chunk_id"],
            next_chunk_id=payload["next_chunk_id"],
            chunk_type=payload["chunk_type"],
            token_count=payload["token_count"],
            content_hash=payload["content_hash"],
            chunker_version=payload["chunker_version"],
            text=payload["text"],
            metadata_json={
                **payload["metadata"],
                "kb_id": document.kb_id,
                "document_id": document.id,
                "visibility": document.visibility,
                "owner_user_id": document.uploaded_by,
            },
        )
        db.add(row)
        chunk_rows.append(row)
    db.flush()

    if chunk_rows:
        document.status = "embedding"
        db.flush()
        texts = [chunk.text for chunk in chunk_rows]
        vectors = await get_embedding_client().embed_texts(texts)
        vector_indexer.upsert(vectors, chunk_rows)
        keyword_indexer.upsert(db, chunk_rows)

    document.status = "need_review" if parse_result.status == "need_review" else "indexed"
    db.commit()
    return {"status": document.status, "chunks": len(chunk_rows)}
