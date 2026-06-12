from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.services.indexing.keyword_indexer as keyword_module
from app.db.base import Base
from app.db.models import Document, DocumentChunk, KnowledgeBase
from app.services.indexing.keyword_indexer import KeywordIndexer, _terms


def test_terms_extracts_searchable_chinese_keyphrases():
    terms = _terms("审计署2024年度授予中小企业合同金额和占比是多少？")

    assert "审计署" in terms
    assert "2024" in terms
    assert "中小企业" in terms
    assert "合同金额" in terms
    assert "占比" in terms
    assert all("是多少" not in term for term in terms)


def test_terms_extracts_procurement_standard_phrases():
    terms = _terms("数据库政府采购需求标准中，数据检索增强功能是否包括中文检索？")

    assert "数据库" in terms
    assert "政府采购" in terms
    assert "需求标准" in terms
    assert "数据检索" in terms
    assert "增强功能" in terms
    assert "中文检索" in terms


def test_bm25_tokenizer_works_without_custom_dictionary():
    assert hasattr(keyword_module, "bm25_tokenize")
    terms = keyword_module.bm25_tokenize("差旅费报销上限为880元，执行率为95%。")

    assert "差旅费" in terms
    assert "差旅" in terms
    assert "报销" in terms
    assert "上限" in terms
    assert "880" in terms
    assert "95%" in terms


def test_keyword_search_uses_bm25_index_before_contains_fallback(monkeypatch):
    db = _session()
    kb = KnowledgeBase(id="kb-bm25", name="制度库", category="制度", visibility="shared")
    target_doc = Document(
        id="doc-target",
        kb_id=kb.id,
        file_name="差旅制度.pdf",
        file_ext="pdf",
        sha256="target",
        status="indexed",
        visibility="shared",
    )
    other_doc = Document(
        id="doc-other",
        kb_id=kb.id,
        file_name="采购制度.pdf",
        file_ext="pdf",
        sha256="other",
        status="indexed",
        visibility="shared",
    )
    target_chunk = DocumentChunk(
        id="chunk-target",
        document_id=target_doc.id,
        kb_id=kb.id,
        text="差旅费报销上限为880元，超过标准需说明原因。",
    )
    other_chunk = DocumentChunk(
        id="chunk-other",
        document_id=other_doc.id,
        kb_id=kb.id,
        text="政府采购合同金额达到限额时，应履行审批流程。",
    )
    db.add_all([kb, target_doc, other_doc, target_chunk, other_chunk])
    db.commit()

    indexer = KeywordIndexer()
    indexer.upsert(db, [target_chunk, other_chunk])
    monkeypatch.setattr(indexer, "_fts_search", lambda *args, **kwargs: [])
    monkeypatch.setattr(indexer, "_contains_search", lambda *args, **kwargs: [])

    results = indexer.search(db, "差旅费报销上限是多少？880元吗？", kb_id=kb.id, top_k=5)

    assert [item["chunk_id"] for item in results] == ["chunk-target"]
    assert results[0]["source"] == "keyword_bm25"


def test_keyword_index_delete_document_removes_bm25_terms(monkeypatch):
    db = _session()
    kb = KnowledgeBase(id="kb-delete", name="制度库", category="制度", visibility="shared")
    document = Document(
        id="doc-delete",
        kb_id=kb.id,
        file_name="差旅制度.pdf",
        file_ext="pdf",
        sha256="delete",
        status="indexed",
        visibility="shared",
    )
    chunk = DocumentChunk(
        id="chunk-delete",
        document_id=document.id,
        kb_id=kb.id,
        text="差旅费报销上限为880元。",
    )
    db.add_all([kb, document, chunk])
    db.commit()

    indexer = KeywordIndexer()
    indexer.upsert(db, [chunk])
    indexer.delete_document(db, document.id)
    monkeypatch.setattr(indexer, "_fts_search", lambda *args, **kwargs: [])
    monkeypatch.setattr(indexer, "_contains_search", lambda *args, **kwargs: [])

    results = indexer.search(db, "差旅费报销上限", kb_id=kb.id, top_k=5)

    assert results == []


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()
