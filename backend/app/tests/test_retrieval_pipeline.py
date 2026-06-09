import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import Document, DocumentChunk, KnowledgeBase, User
from app.services.indexing.vector_indexer import VectorIndexer
from app.services.rag import retriever


class FakeEmbeddingClient:
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_vector_indexer_returns_empty_when_index_has_no_vectors():
    db = _session()
    kb = KnowledgeBase(id="kb-1", name="共享库", category="共享库", visibility="shared")
    document = Document(
        id="doc-1",
        kb_id=kb.id,
        file_name="制度.docx",
        file_ext="docx",
        sha256="x",
        status="indexed",
        visibility="shared",
    )
    chunk = DocumentChunk(id="chunk-1", document_id=document.id, text="设备采购应履行审批。")
    db.add_all([kb, document, chunk])
    db.commit()

    results = VectorIndexer().search([1.0, 0.0], db=db, top_k=5, kb_id=kb.id)

    assert results == []


@pytest.mark.asyncio
async def test_retrieve_evidence_filters_vector_results_by_knowledge_base(monkeypatch):
    db = _session()
    allowed_kb = KnowledgeBase(id="kb-allowed", name="允许库", category="允许库", visibility="shared")
    forbidden_kb = KnowledgeBase(id="kb-forbidden", name="其他库", category="其他库", visibility="shared")
    allowed_doc = Document(
        id="doc-allowed",
        kb_id=allowed_kb.id,
        file_name="允许制度.docx",
        file_ext="docx",
        sha256="a",
        status="indexed",
        visibility="shared",
    )
    forbidden_doc = Document(
        id="doc-forbidden",
        kb_id=forbidden_kb.id,
        file_name="其他制度.docx",
        file_ext="docx",
        sha256="b",
        status="indexed",
        visibility="shared",
    )
    allowed_chunk = DocumentChunk(
        id="chunk-allowed",
        document_id=allowed_doc.id,
        text="允许库材料：采购审批记录应保存。",
        metadata_json={"page_number": 1},
    )
    forbidden_chunk = DocumentChunk(
        id="chunk-forbidden",
        document_id=forbidden_doc.id,
        text="其他库材料：这个片段向量分数更高。",
        metadata_json={"page_number": 2},
    )
    db.add_all([allowed_kb, forbidden_kb, allowed_doc, forbidden_doc, allowed_chunk, forbidden_chunk])
    db.commit()

    indexer = VectorIndexer()
    indexer.upsert([[0.5, 0.0], [1.0, 0.0]], [allowed_chunk, forbidden_chunk])
    monkeypatch.setattr(retriever, "vector_indexer", indexer)
    monkeypatch.setattr(retriever, "get_embedding_client", lambda: FakeEmbeddingClient())

    evidence = await retriever.retrieve_evidence(db, "完全无关键词", kb_id=allowed_kb.id, top_k=5)

    assert [item["chunk_id"] for item in evidence] == ["chunk-allowed"]
    assert evidence[0]["file_name"] == "允许制度.docx"


@pytest.mark.asyncio
async def test_retrieve_evidence_accepts_multiple_knowledge_bases(monkeypatch):
    db = _session()
    first_kb = KnowledgeBase(id="kb-first", name="第一库", category="第一库", visibility="shared")
    second_kb = KnowledgeBase(id="kb-second", name="第二库", category="第二库", visibility="shared")
    excluded_kb = KnowledgeBase(id="kb-excluded", name="排除库", category="排除库", visibility="shared")
    first_doc = Document(
        id="doc-first",
        kb_id=first_kb.id,
        file_name="第一制度.docx",
        file_ext="docx",
        sha256="a",
        status="indexed",
        visibility="shared",
    )
    second_doc = Document(
        id="doc-second",
        kb_id=second_kb.id,
        file_name="第二制度.docx",
        file_ext="docx",
        sha256="b",
        status="indexed",
        visibility="shared",
    )
    excluded_doc = Document(
        id="doc-excluded",
        kb_id=excluded_kb.id,
        file_name="排除制度.docx",
        file_ext="docx",
        sha256="c",
        status="indexed",
        visibility="shared",
    )
    first_chunk = DocumentChunk(
        id="chunk-first",
        document_id=first_doc.id,
        kb_id=first_kb.id,
        text="第一库材料：采购申请应说明预算。",
    )
    second_chunk = DocumentChunk(
        id="chunk-second",
        document_id=second_doc.id,
        kb_id=second_kb.id,
        text="第二库材料：采购审批应保留记录。",
    )
    excluded_chunk = DocumentChunk(
        id="chunk-excluded",
        document_id=excluded_doc.id,
        kb_id=excluded_kb.id,
        text="排除库材料：不应该被召回。",
    )
    db.add_all([
        first_kb,
        second_kb,
        excluded_kb,
        first_doc,
        second_doc,
        excluded_doc,
        first_chunk,
        second_chunk,
        excluded_chunk,
    ])
    db.commit()

    indexer = VectorIndexer()
    indexer.upsert([[0.9, 0.0], [0.8, 0.0], [1.0, 0.0]], [first_chunk, second_chunk, excluded_chunk])
    monkeypatch.setattr(retriever, "vector_indexer", indexer)
    monkeypatch.setattr(retriever, "get_embedding_client", lambda: FakeEmbeddingClient())

    evidence = await retriever.retrieve_evidence(
        db,
        "完全无关键词",
        kb_ids=[first_kb.id, second_kb.id],
        top_k=5,
    )

    assert {item["chunk_id"] for item in evidence} == {"chunk-first", "chunk-second"}


@pytest.mark.asyncio
async def test_retrieve_evidence_rejects_invisible_explicit_private_kb(monkeypatch):
    db = _session()
    user = User(id="u1", username="auditor", password_hash="x", role="auditor", display_name="审计人员")
    private_kb = KnowledgeBase(
        id="kb-private",
        name="他人私有库",
        category="私有",
        visibility="private",
        created_by="u2",
    )
    document = Document(
        id="doc-private",
        kb_id=private_kb.id,
        file_name="他人制度.docx",
        file_ext="docx",
        sha256="p",
        status="indexed",
        visibility="private",
        uploaded_by="u2",
    )
    chunk = DocumentChunk(
        id="chunk-private",
        document_id=document.id,
        kb_id=private_kb.id,
        text="他人私有库材料不应被召回。",
        metadata_json={"page_number": 1},
    )
    db.add_all([user, private_kb, document, chunk])
    db.commit()

    indexer = VectorIndexer()
    indexer.upsert([[1.0, 0.0]], [chunk])
    monkeypatch.setattr(retriever, "vector_indexer", indexer)
    monkeypatch.setattr(retriever, "get_embedding_client", lambda: FakeEmbeddingClient())

    evidence = await retriever.retrieve_evidence(db, "他人私有库", kb_id=private_kb.id, current_user=user)

    assert evidence == []
