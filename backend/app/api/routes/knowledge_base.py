from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_user
from app.db.models import Document, KnowledgeBase, User
from app.db.session import get_db
from app.schemas.common import ok
from app.schemas.knowledge_base import KnowledgeBaseCreate
from app.services.indexing.keyword_indexer import keyword_indexer
from app.services.indexing.vector_indexer import vector_indexer
from app.services.permissions.permission_service import can_manage_shared_kb, visible_kb_filter

router = APIRouter(prefix="/kb", tags=["knowledge_base"])


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
        "uploaded_by": doc.uploaded_by,
        "created_at": doc.created_at.isoformat(),
    }


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
