"""add keyword bm25 index tables

Revision ID: 20260612_0006
Revises: 20260612_0005
Create Date: 2026-06-12
"""

import sqlalchemy as sa
from alembic import op

revision = "20260612_0006"
down_revision = "20260612_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing_tables = set(sa.inspect(bind).get_table_names())
    if "document_chunk_keyword_stats" not in existing_tables:
        op.create_table(
            "document_chunk_keyword_stats",
            sa.Column("chunk_id", sa.String(length=36), sa.ForeignKey("document_chunks.id"), primary_key=True),
            sa.Column("document_id", sa.String(length=36), sa.ForeignKey("documents.id"), nullable=False),
            sa.Column("kb_id", sa.String(length=36), nullable=True),
            sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        )
    if "document_chunk_terms" not in existing_tables:
        op.create_table(
            "document_chunk_terms",
            sa.Column("chunk_id", sa.String(length=36), sa.ForeignKey("document_chunks.id"), primary_key=True),
            sa.Column("term", sa.String(length=120), primary_key=True),
            sa.Column("document_id", sa.String(length=36), sa.ForeignKey("documents.id"), nullable=False),
            sa.Column("kb_id", sa.String(length=36), nullable=True),
            sa.Column("tf", sa.Integer(), nullable=False, server_default="1"),
        )

    _create_index("document_chunk_keyword_stats", "ix_document_chunk_keyword_stats_document_id", ["document_id"])
    _create_index("document_chunk_keyword_stats", "ix_document_chunk_keyword_stats_kb_id", ["kb_id"])
    _create_index("document_chunk_terms", "ix_document_chunk_terms_document_id", ["document_id"])
    _create_index("document_chunk_terms", "ix_document_chunk_terms_kb_id", ["kb_id"])
    _create_index("document_chunk_terms", "ix_document_chunk_terms_term_chunk", ["term", "chunk_id"])
    _create_index("document_chunk_terms", "ix_document_chunk_terms_document_term", ["document_id", "term"])


def downgrade() -> None:
    op.drop_index("ix_document_chunk_terms_document_term", table_name="document_chunk_terms")
    op.drop_index("ix_document_chunk_terms_term_chunk", table_name="document_chunk_terms")
    op.drop_index("ix_document_chunk_terms_kb_id", table_name="document_chunk_terms")
    op.drop_index("ix_document_chunk_terms_document_id", table_name="document_chunk_terms")
    op.drop_index("ix_document_chunk_keyword_stats_kb_id", table_name="document_chunk_keyword_stats")
    op.drop_index("ix_document_chunk_keyword_stats_document_id", table_name="document_chunk_keyword_stats")
    op.drop_table("document_chunk_terms")
    op.drop_table("document_chunk_keyword_stats")


def _create_index(table_name: str, index_name: str, columns: list[str]) -> None:
    existing_indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}
    if index_name not in existing_indexes:
        op.create_index(index_name, table_name, columns)
