"""add rag chunk metadata

Revision ID: 20260609_0003
Revises: 20260609_0002
Create Date: 2026-06-09
"""

import sqlalchemy as sa
from alembic import op

from app.db.models import json_type

revision = "20260609_0003"
down_revision = "20260609_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing_columns = {column["name"] for column in sa.inspect(bind).get_columns("document_chunks")}
    columns = [
        sa.Column("kb_id", sa.String(length=36), nullable=True),
        sa.Column("parent_chunk_id", sa.String(length=80), nullable=True),
        sa.Column("prev_chunk_id", sa.String(length=80), nullable=True),
        sa.Column("next_chunk_id", sa.String(length=80), nullable=True),
        sa.Column("chunk_type", sa.String(length=40), nullable=False, server_default="paragraph"),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("chunker_version", sa.String(length=40), nullable=False, server_default="structured-v1"),
        sa.Column("embedding_json", json_type(), nullable=True),
    ]
    with op.batch_alter_table("document_chunks") as batch:
        for column in columns:
            if column.name not in existing_columns:
                batch.add_column(column)

    existing_indexes = {index["name"] for index in sa.inspect(bind).get_indexes("document_chunks")}
    _create_index(existing_indexes, "ix_document_chunks_kb_id", ["kb_id"])
    _create_index(existing_indexes, "ix_document_chunks_parent_chunk_id", ["parent_chunk_id"])
    _create_index(existing_indexes, "ix_document_chunks_chunk_type", ["chunk_type"])
    _create_index(existing_indexes, "ix_document_chunks_content_hash", ["content_hash"])

    bind.execute(
        sa.text(
            """
            update document_chunks
            set kb_id = (
                select documents.kb_id
                from documents
                where documents.id = document_chunks.document_id
            )
            where kb_id is null
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_document_chunks_content_hash", table_name="document_chunks")
    op.drop_index("ix_document_chunks_chunk_type", table_name="document_chunks")
    op.drop_index("ix_document_chunks_parent_chunk_id", table_name="document_chunks")
    op.drop_index("ix_document_chunks_kb_id", table_name="document_chunks")
    with op.batch_alter_table("document_chunks") as batch:
        batch.drop_column("embedding_json")
        batch.drop_column("chunker_version")
        batch.drop_column("content_hash")
        batch.drop_column("token_count")
        batch.drop_column("chunk_type")
        batch.drop_column("next_chunk_id")
        batch.drop_column("prev_chunk_id")
        batch.drop_column("parent_chunk_id")
        batch.drop_column("kb_id")


def _create_index(existing_indexes: set[str], name: str, columns: list[str]) -> None:
    if name not in existing_indexes:
        op.create_index(name, "document_chunks", columns)
