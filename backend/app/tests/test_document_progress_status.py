from datetime import UTC, datetime

from app.api.routes.knowledge_base import _doc_dict
from app.db.models import Document


def test_document_dict_exposes_stage_progress_for_embedding_document():
    document = Document(
        id="doc-progress",
        kb_id="kb-progress",
        file_name="制度.pdf",
        file_ext="pdf",
        file_size=1024,
        status="embedding",
        error_message="切分完成，正在生成 embedding 并写入向量/关键词索引。",
        visibility="private",
        version=1,
        is_current_version=True,
        created_at=datetime.now(UTC),
    )

    payload = _doc_dict(document)

    assert payload["progress_stage"] == "索引中"
    assert payload["progress_percent"] == 88


def test_document_dict_prefers_metadata_progress_for_parsing_document():
    document = Document(
        id="doc-progress",
        kb_id="kb-progress",
        file_name="制度.pdf",
        file_ext="pdf",
        file_size=1024,
        status="parsing",
        error_message="MinerU 正在解析。",
        visibility="private",
        version=1,
        is_current_version=True,
        created_at=datetime.now(UTC),
        metadata_json={
            "progress_stage": "解析中（20/600 页）",
            "progress_percent": 3,
            "completed_pages": 20,
            "page_count": 600,
        },
    )

    payload = _doc_dict(document)

    assert payload["progress_stage"] == "解析中（20/600 页）"
    assert payload["progress_percent"] == 3
