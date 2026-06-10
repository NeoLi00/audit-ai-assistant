from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_user
from app.api.routes.knowledge_base import _doc_dict
from app.core.config import get_settings
from app.db.models import Document, DocumentBlock, DocumentChunk, KnowledgeBase, User
from app.db.session import get_db
from app.schemas.common import ok
from app.schemas.document import OcrCorrectionRequest
from app.services.audit.audit_logger import log_action
from app.services.indexing.keyword_indexer import keyword_indexer
from app.services.indexing.vector_indexer import vector_indexer
from app.services.parser.document_parser import SUPPORTED_EXTENSIONS
from app.services.permissions.permission_service import can_manage_shared_kb, can_upload_to_kb
from app.services.storage.minio_client import ObjectStorage
from app.services.tasks.document_tasks import (
    process_document,
    process_document_in_background,
    process_document_task,
    sha256_file,
)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    kb_id: str | None = Form(default=None),
    department_category: str = Form(default=""),
    business_type: str = Form(default=""),
    tags: str = Form(default=""),
    visibility: str = Form(default="department"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    settings = get_settings()
    ext = Path(file.filename or "").suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="当前格式不支持，请上传Word/Excel/PDF/图片文件")
    if not kb_id:
        raise HTTPException(status_code=400, detail="请选择知识库")
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    if not can_upload_to_kb(current_user, kb):
        raise HTTPException(status_code=403, detail="普通用户只能上传到自己的个人知识库")
    object_key, local_path = await ObjectStorage(settings).save_upload(file)
    size = local_path.stat().st_size
    if size > settings.max_upload_bytes:
        local_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="单文件大小不能超过50MB")
    document = Document(
        kb_id=kb_id,
        file_name=file.filename or local_path.name,
        file_ext=ext.lstrip("."),
        mime_type=file.content_type or "",
        file_size=size,
        sha256=sha256_file(local_path),
        minio_bucket=settings.minio_bucket,
        minio_object_key=object_key,
        department_category=kb.name if kb.visibility == "shared" else department_category,
        business_type=business_type,
        tags=[tag.strip() for tag in tags.split(",") if tag.strip()],
        visibility=kb.visibility,
        uploaded_by=current_user.id,
        status="uploaded",
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    log_action(db, "上传文件", current_user.id, "document", document.id, {"file_name": document.file_name})
    if settings.process_documents_inline:
        background_tasks.add_task(process_document_in_background, document.id)
    else:
        process_document_task.delay(document.id)
    return ok(_doc_dict(document))


@router.get("")
def list_documents(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    documents = db.query(Document).order_by(Document.created_at.desc()).limit(200).all()
    return ok([_doc_dict(doc) for doc in documents])


@router.get("/{document_id}")
def get_document(document_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")
    return ok(_doc_dict(document))


@router.delete("/{document_id}")
def delete_document(document_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")
    kb = db.get(KnowledgeBase, document.kb_id) if document.kb_id else None
    can_delete = can_manage_shared_kb(current_user) or (
        document.visibility == "private"
        and (document.uploaded_by == current_user.id or (kb is not None and kb.created_by == current_user.id))
    )
    if not can_delete:
        raise HTTPException(status_code=403, detail="无权删除该文档")

    file_name = document.file_name
    keyword_indexer.delete_document(db, document.id)
    vector_indexer.delete_document(document.id)
    ObjectStorage(get_settings()).remove(document.minio_object_key)
    db.delete(document)
    db.commit()
    log_action(db, "删除文档", current_user.id, "document", document_id, {"file_name": file_name})
    return ok({"deleted": document_id})


@router.get("/{document_id}/blocks")
def get_blocks(document_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    blocks = (
        db.query(DocumentBlock)
        .filter(DocumentBlock.document_id == document_id)
        .order_by(DocumentBlock.created_at)
        .all()
    )
    return ok(
        [
            {
                "id": block.id,
                "block_type": block.block_type,
                "page_number": block.page_number,
                "sheet_name": block.sheet_name,
                "heading_path": block.heading_path,
                "text": block.text,
                "confidence": block.confidence,
            }
            for block in blocks
        ]
    )


@router.get("/{document_id}/chunks")
def get_chunks(document_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
        .all()
    )
    return ok(
        [
            {
                "id": chunk.id,
                "chunk_index": chunk.chunk_index,
                "parent_chunk_id": chunk.parent_chunk_id,
                "prev_chunk_id": chunk.prev_chunk_id,
                "next_chunk_id": chunk.next_chunk_id,
                "chunk_type": chunk.chunk_type,
                "token_count": chunk.token_count,
                "content_hash": chunk.content_hash,
                "chunker_version": chunk.chunker_version,
                "text": chunk.text,
                "metadata": chunk.metadata_json,
            }
            for chunk in chunks
        ]
    )


@router.post("/{document_id}/reindex")
def reindex(document_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = process_document(db, document_id)
    log_action(db, "文档重新入库", current_user.id, "document", document_id, result)
    return ok(result)


@router.post("/{document_id}/ocr-correction")
def ocr_correction(
    document_id: str,
    payload: OcrCorrectionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")
    document.status = "parsing"
    document.error_message = ""
    db.query(DocumentBlock).filter(DocumentBlock.document_id == document_id).delete()
    db.add(DocumentBlock(document_id=document_id, block_type="ocr_correction", text=payload.text, confidence=1.0))
    db.commit()
    result = process_document(db, document_id)
    log_action(db, "OCR 校对", current_user.id, "document", document_id)
    return ok(result)
