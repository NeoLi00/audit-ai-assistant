from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import KnowledgeBase, User
from app.db.seed import seed_defaults
from app.services.permissions.permission_service import can_upload_to_kb, visible_kb_filter


def test_seed_creates_default_users_without_preset_knowledge_categories():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    seed_defaults(session)

    assert session.query(User).count() == 3
    assert session.query(KnowledgeBase).count() == 0


def test_regular_user_can_upload_only_to_own_private_knowledge_base():
    user = User(id="u1", username="auditor", role="auditor", display_name="审计人员")
    own_private = KnowledgeBase(id="kb1", name="个人", visibility="private", created_by="u1")
    shared = KnowledgeBase(id="kb2", name="共享", visibility="shared", created_by="admin")
    other_private = KnowledgeBase(id="kb3", name="他人", visibility="private", created_by="u2")

    assert can_upload_to_kb(user, own_private)
    assert not can_upload_to_kb(user, shared)
    assert not can_upload_to_kb(user, other_private)


def test_system_admin_can_upload_to_shared_knowledge_base():
    admin = User(id="admin", username="admin", role="system_admin", display_name="管理员")
    shared = KnowledgeBase(id="kb2", name="共享", visibility="shared", created_by="admin")

    assert can_upload_to_kb(admin, shared)


def test_visible_kb_filter_allows_shared_and_own_private_for_regular_user():
    user = User(id="u1", username="auditor", role="auditor", display_name="审计人员")

    assert visible_kb_filter(user, KnowledgeBase(id="kb1", visibility="private", created_by="u1"))
    assert visible_kb_filter(user, KnowledgeBase(id="kb2", visibility="shared", created_by="admin"))
    assert not visible_kb_filter(user, KnowledgeBase(id="kb3", visibility="private", created_by="u2"))
