from app.db.models import Document, KnowledgeBase, User


def can_view_document(user: User, document: Document) -> bool:
    if user.role in {"system_admin", "audit_manager"}:
        return True
    if document.visibility == "public":
        return True
    if document.visibility == "private":
        return document.uploaded_by == user.id
    return document.department_category in {"", user.department, "审计处"} or document.uploaded_by == user.id


def can_admin(user: User) -> bool:
    return user.role in {"system_admin", "audit_manager"}


def can_manage_shared_kb(user: User) -> bool:
    return user.role == "system_admin"


def visible_kb_filter(user: User, kb: KnowledgeBase) -> bool:
    if user.role == "system_admin":
        return True
    if kb.visibility == "shared":
        return True
    return kb.visibility == "private" and kb.created_by == user.id


def can_upload_to_kb(user: User, kb: KnowledgeBase) -> bool:
    if kb.visibility == "shared":
        return can_manage_shared_kb(user)
    if kb.visibility == "private":
        return kb.created_by == user.id or user.role == "system_admin"
    return user.role == "system_admin"
