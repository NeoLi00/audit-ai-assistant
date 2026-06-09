from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.db.base import Base
from app.db.models import Document, KnowledgeBase, User
from app.db.schema import ensure_local_schema
from app.db.session import SessionLocal, engine

DEFAULT_USERS = [
    ("admin", "admin123", "系统管理员", "system_admin"),
    ("auditor", "auditor123", "审计人员", "auditor"),
    ("manager", "manager123", "审计经理", "audit_manager"),
]

LEGACY_PRESET_KB_NAMES = {
    "我的上传",
    "招标采购",
    "资产管理",
    "财务收支",
    "工程建设",
    "后勤管理",
    "科研经费",
    "合同管理",
    "历史审计资料",
}


def seed_defaults(db: Session) -> None:
    for username, password, display_name, role in DEFAULT_USERS:
        user = db.query(User).filter(User.username == username).one_or_none()
        if user is None:
            db.add(
                User(
                    username=username,
                    password_hash=get_password_hash(password),
                    display_name=display_name,
                    role=role,
                    department="审计处",
                )
            )
    db.flush()

    for kb in db.query(KnowledgeBase).filter(KnowledgeBase.name.in_(LEGACY_PRESET_KB_NAMES)).all():
        has_documents = db.query(Document).filter(Document.kb_id == kb.id).first() is not None
        if not has_documents:
            db.delete(kb)
    db.commit()


if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    ensure_local_schema(engine)
    with SessionLocal() as session:
        seed_defaults(session)
        print("Seed data ready.")
