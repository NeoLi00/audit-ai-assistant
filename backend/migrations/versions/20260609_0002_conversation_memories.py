"""add conversation memories

Revision ID: 20260609_0002
Revises: 20260609_0001
Create Date: 2026-06-09
"""

from alembic import op

from app.db.models import ConversationMemory

revision = "20260609_0002"
down_revision = "20260609_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    ConversationMemory.__table__.create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    ConversationMemory.__table__.drop(bind, checkfirst=True)

