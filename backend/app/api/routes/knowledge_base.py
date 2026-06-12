from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_user
from app.core.config import get_settings
from app.db.models import Document, KnowledgeBase, User
from app.db.session import get_db
from app.schemas.common import ok
from app.schemas.knowledge_base import KnowledgeBaseCreate
from app.services.indexing.keyword_indexer import keyword_indexer
from app.services.indexing.vector_indexer import vector_indexer
from app.services.parser.progress import progress_for_status
from app.services.permissions.permission_service import can_manage_shared_kb, visible_kb_filter

router = APIRouter(prefix="/kb", tags=["knowledge_base"])

MINERU_STATUS_MESSAGE = (
    "MinerU 正在解析：版面分析、表格结构识别、图片/扫描件 OCR 文字识别运行中；"
    "首次加载模型或大文件可能需要较长时间。"
)
MINERU_PARSER_DETAIL = "能力：版面分析、表格结构识别、图片/扫描件 OCR 文字识别、公式/印章等视觉元素检测。"


@router.get("")
def list_kb(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    ensure_personal_kb(db, current_user)
    items = db.query(KnowledgeBase).order_by(KnowledgeBase.created_at).all()
    return ok([_kb_dict(item) for item in items if visible_kb_filter(current_user, item)])


@router.post("")
def create_kb(
    payload: KnowledgeBaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.visibility == "shared" and not can_manage_shared_kb(current_user):
        raise HTTPException(status_code=403, detail="只有系统管理员可以创建共享知识库")
    visibility = payload.visibility if payload.visibility in {"shared", "private"} else "private"
    kb = KnowledgeBase(
        name=payload.name,
        description=payload.description,
        category=payload.category or payload.name,
        visibility=visibility,
        created_by=current_user.id,
    )
    db.add(kb)
    db.commit()
    db.refresh(kb)
    return ok(_kb_dict(kb))


@router.get("/{kb_id}")
def get_kb(kb_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        return ok(None)
    if not visible_kb_filter(current_user, kb):
        raise HTTPException(status_code=403, detail="无权访问该知识库")
    return ok(_kb_dict(kb))


@router.delete("/{kb_id}")
def delete_kb(kb_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not can_manage_shared_kb(current_user):
        raise HTTPException(status_code=403, detail="只有系统管理员可以删除知识库")
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    keyword_indexer.delete_kb(db, kb_id)
    vector_indexer.delete_kb(kb_id)
    documents = db.query(Document).filter(Document.kb_id == kb_id).all()
    for document in documents:
        db.delete(document)
    db.delete(kb)
    db.commit()
    return ok({"deleted": kb_id})


@router.get("/{kb_id}/documents")
def kb_documents(kb_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    if not visible_kb_filter(current_user, kb):
        raise HTTPException(status_code=403, detail="无权访问该知识库")
    documents = db.query(Document).filter(Document.kb_id == kb_id).order_by(Document.created_at.desc()).all()
    return ok([_doc_dict(doc) for doc in documents])


def _kb_dict(kb: KnowledgeBase) -> dict:
    return {
        "id": kb.id,
        "name": kb.name,
        "description": kb.description,
        "category": kb.category,
        "visibility": kb.visibility,
        "created_by": kb.created_by,
    }


def _doc_dict(doc: Document) -> dict:
    metadata = doc.metadata_json or {}
    parser_detail = metadata.get("parser_detail") or _document_parser_detail(doc)
    progress = progress_for_status(doc.status, metadata)
    return {
        "id": doc.id,
        "kb_id": doc.kb_id,
        "file_name": doc.file_name,
        "file_ext": doc.file_ext,
        "file_size": doc.file_size,
        "department_category": doc.department_category,
        "business_type": doc.business_type,
        "tags": doc.tags,
        "visibility": doc.visibility,
        "version": doc.version,
        "is_current_version": doc.is_current_version,
        "status": doc.status,
        "error_message": doc.error_message,
        "status_message": _document_status_message(doc),
        "parser_provider": get_settings().document_parser_provider,
        "parser_detail": parser_detail,
        **progress,
        "uploaded_by": doc.uploaded_by,
        "created_at": doc.created_at.isoformat(),
    }


def _document_status_message(doc: Document) -> str:
    if doc.status == "failed":
        return f"解析失败：{doc.error_message}" if doc.error_message else "解析失败。"
    if doc.status == "need_review":
        return f"解析完成但需要人工复核：{doc.error_message}" if doc.error_message else "解析结果需要人工复核。"
    if doc.error_message:
        return doc.error_message
    if doc.status == "uploaded":
        return "文件已上传，等待进入解析队列。"
    if doc.status == "parsing":
        return MINERU_STATUS_MESSAGE if get_settings().document_parser_provider == "mineru" else "正在解析文件内容。"
    if doc.status == "chunking":
        return "解析完成，正在进行结构化切分。"
    if doc.status == "embedding":
        return "切分完成，正在生成 embedding 并写入向量/关键词索引。"
    if doc.status == "indexed":
        return "已完成解析、切分和索引。"
    return ""


def _document_parser_detail(doc: Document) -> str:
    settings = get_settings()
    provider = settings.document_parser_provider
    if provider == "mineru":
        timeout = int(settings.mineru_timeout or 0)
        timeout_text = "无后端超时限制" if timeout <= 0 else f"后端超时 {timeout} 秒"
        batch_size = int(settings.mineru_page_batch_size or 0)
        batch_text = f"PDF 每 {batch_size} 页分段解析" if batch_size > 0 else "PDF 不分段解析"
        return f"文件类型：{doc.file_ext or 'unknown'}；{MINERU_PARSER_DETAIL}；{timeout_text}；{batch_text}。"
    return f"文件类型：{doc.file_ext or 'unknown'}；解析器：{provider}。"


def ensure_personal_kb(db: Session, user: User) -> KnowledgeBase:
    kb = (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.visibility == "private",
            KnowledgeBase.created_by == user.id,
        )
        .order_by(KnowledgeBase.created_at.asc())
        .first()
    )
    if kb:
        return kb
    kb = KnowledgeBase(
        name=f"{user.display_name or user.username}的个人知识库",
        description="仅本人可见和上传的个人知识库",
        category="个人知识库",
        visibility="private",
        created_by=user.id,
    )
    db.add(kb)
    db.commit()
    db.refresh(kb)
    return kb
