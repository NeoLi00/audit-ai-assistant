import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import Document, DocumentChunk, KnowledgeBase
from app.services.parser.base import ParsedBlock, ParseResult
from app.services.tasks import document_tasks


@pytest.mark.asyncio
async def test_process_document_commits_chunks_before_embedding(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'processing.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-1.4")

    with session_factory() as db:
        kb = KnowledgeBase(id="kb-process", name="处理测试库", category="测试", visibility="private")
        document = Document(
            id="doc-process",
            kb_id=kb.id,
            file_name="source.pdf",
            file_ext="pdf",
            sha256="sha",
            minio_object_key="documents/source.pdf",
            status="uploaded",
            visibility="private",
        )
        db.add_all([kb, document])
        db.commit()

    class FakeStorage:
        def local_path_for(self, object_key: str):
            return source

    class FakeParser:
        def parse(self, path):
            return ParseResult(
                status="ready",
                text="审计测试文本",
                blocks=[
                    ParsedBlock(text="第一段：采购预算超过 50 万元需要复核。"),
                    ParsedBlock(text="第二段：复核记录应当归档。"),
                ],
            )

    class FakeEmbeddingClient:
        async def embed_texts(self, texts: list[str]) -> list[list[float]]:
            with session_factory() as check_db:
                visible_chunks = (
                    check_db.query(DocumentChunk).filter(DocumentChunk.document_id == "doc-process").count()
                )
                visible_document = check_db.get(Document, "doc-process")
            assert visible_chunks > 0
            assert visible_document is not None
            assert visible_document.status == "embedding"
            return [[1.0, 0.0] for _ in texts]

    class FakeVectorIndexer:
        def delete_document(self, document_id: str) -> None:
            pass

        def upsert(self, vectors, chunks) -> None:
            for chunk, vector in zip(chunks, vectors, strict=False):
                chunk.embedding_json = vector

    class FakeKeywordIndexer:
        def delete_document(self, db, document_id: str) -> None:
            pass

        def upsert(self, db, chunks) -> None:
            pass

    monkeypatch.setattr(document_tasks, "ObjectStorage", lambda: FakeStorage())
    monkeypatch.setattr(document_tasks, "DocumentParser", lambda: FakeParser())
    monkeypatch.setattr(document_tasks, "get_embedding_client", lambda: FakeEmbeddingClient())
    monkeypatch.setattr(document_tasks, "vector_indexer", FakeVectorIndexer())
    monkeypatch.setattr(document_tasks, "keyword_indexer", FakeKeywordIndexer())

    with session_factory() as db:
        result = await document_tasks.process_document_async(db, "doc-process")

    assert result["status"] == "indexed"
