from sqlalchemy import inspect, text

SQLITE_DOCUMENT_CHUNK_COLUMNS: dict[str, str] = {
    "kb_id": "VARCHAR(36)",
    "parent_chunk_id": "VARCHAR(80)",
    "prev_chunk_id": "VARCHAR(80)",
    "next_chunk_id": "VARCHAR(80)",
    "chunk_type": "VARCHAR(40) DEFAULT 'paragraph' NOT NULL",
    "token_count": "INTEGER DEFAULT 0 NOT NULL",
    "content_hash": "VARCHAR(64) DEFAULT '' NOT NULL",
    "chunker_version": "VARCHAR(40) DEFAULT 'structured-v1' NOT NULL",
    "embedding_json": "JSON",
}


def ensure_local_schema(engine) -> None:
    if engine.dialect.name != "sqlite":
        return
    inspector = inspect(engine)
    if "document_chunks" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("document_chunks")}
    with engine.begin() as connection:
        for column_name, ddl in SQLITE_DOCUMENT_CHUNK_COLUMNS.items():
            if column_name not in existing:
                connection.execute(text(f"alter table document_chunks add column {column_name} {ddl}"))
        _create_index(connection, "ix_document_chunks_kb_id", "document_chunks", "kb_id")
        _create_index(connection, "ix_document_chunks_parent_chunk_id", "document_chunks", "parent_chunk_id")
        _create_index(connection, "ix_document_chunks_chunk_type", "document_chunks", "chunk_type")
        _create_index(connection, "ix_document_chunks_content_hash", "document_chunks", "content_hash")
        connection.execute(
            text(
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


def _create_index(connection, index_name: str, table_name: str, column_name: str) -> None:
    connection.execute(text(f"create index if not exists {index_name} on {table_name} ({column_name})"))
