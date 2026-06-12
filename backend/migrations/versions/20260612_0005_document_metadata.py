"""add document metadata

Revision ID: 20260612_0005
Revises: 20260610_0004
Create Date: 2026-06-12
"""

import sqlalchemy as sa
from alembic import op

from app.db.models import json_type

revision = "20260612_0005"
down_revision = "20260610_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing_columns = {column["name"] for column in sa.inspect(bind).get_columns("documents")}
    if "metadata_json" not in existing_columns:
        with op.batch_alter_table("documents") as batch:
            batch.add_column(sa.Column("metadata_json", json_type(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("documents") as batch:
        batch.drop_column("metadata_json")
