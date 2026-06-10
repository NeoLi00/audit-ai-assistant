from fastapi.testclient import TestClient

from app.api.routes import document as document_routes
from app.core import config as core_config
from app.db.models import Document, DocumentBlock, DocumentChunk
from app.db.session import SessionLocal
from app.main import app
from app.services.indexing import keyword_indexer, vector_indexer
from app.services.model_gateway import runtime_config


def _login(client: TestClient, username: str, password: str) -> dict[str, str]:
    token = client.post("/api/auth/login", json={"username": username, "password": password}).json()[
        "data"
    ]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_admin_database_overview_reports_core_tables():
    client = TestClient(app)
    with client:
        headers = _login(client, "admin", "admin123")
        response = client.get("/api/admin/database/overview", headers=headers)

    assert response.status_code == 200
    tables = {item["table"] for item in response.json()["data"]["tables"]}
    assert {"users", "knowledge_bases", "documents", "document_chunks"}.issubset(tables)


def test_system_admin_can_delete_knowledge_base():
    client = TestClient(app)
    with client:
        headers = _login(client, "admin", "admin123")
        created = client.post(
            "/api/kb",
            headers=headers,
            json={"name": "待删除知识库", "visibility": "shared"},
        ).json()["data"]
        deleted = client.delete(f"/api/kb/{created['id']}", headers=headers)

    assert deleted.status_code == 200
    assert deleted.json()["data"]["deleted"] == created["id"]


def test_system_admin_can_delete_document_and_indexes(tmp_path, monkeypatch):
    deleted_keyword: list[str] = []
    deleted_vector: list[str] = []

    monkeypatch.setattr(
        core_config,
        "get_settings",
        lambda: core_config.Settings(local_storage_dir=tmp_path, use_local_storage_fallback=True),
    )
    monkeypatch.setattr(
        document_routes,
        "get_settings",
        lambda: core_config.Settings(local_storage_dir=tmp_path, use_local_storage_fallback=True),
    )
    monkeypatch.setattr(
        keyword_indexer.keyword_indexer,
        "delete_document",
        lambda db, doc_id: deleted_keyword.append(doc_id),
    )
    monkeypatch.setattr(vector_indexer.vector_indexer, "delete_document", lambda doc_id: deleted_vector.append(doc_id))

    client = TestClient(app)
    with client:
        headers = _login(client, "admin", "admin123")
        created_kb = client.post(
            "/api/kb",
            headers=headers,
            json={"name": "文档删除测试库", "visibility": "shared"},
        ).json()["data"]
        stored_file = tmp_path / "documents" / "delete-me.pdf"
        stored_file.parent.mkdir(parents=True, exist_ok=True)
        stored_file.write_bytes(b"%PDF-1.4")
        with SessionLocal() as db:
            document = Document(
                kb_id=created_kb["id"],
                file_name="delete-me.pdf",
                file_ext="pdf",
                minio_object_key="documents/delete-me.pdf",
                sha256="abc",
                visibility="shared",
                uploaded_by="admin-user",
                status="indexed",
            )
            db.add(document)
            db.flush()
            db.add(DocumentBlock(document_id=document.id, block_type="paragraph", text="待删除块"))
            db.add(DocumentChunk(document_id=document.id, kb_id=created_kb["id"], chunk_index=0, text="待删除切片"))
            document_id = document.id
            db.commit()

        response = client.delete(f"/api/documents/{document_id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["data"]["deleted"] == document_id
    assert deleted_keyword == [document_id]
    assert deleted_vector == [document_id]
    assert not stored_file.exists()
    with SessionLocal() as db:
        assert db.get(Document, document_id) is None
        assert db.query(DocumentBlock).filter(DocumentBlock.document_id == document_id).count() == 0
        assert db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).count() == 0


def test_model_setup_accepts_deepseek_config_without_exposing_api_key(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_config, "RUNTIME_CONFIG_PATH", tmp_path / ".runtime_model_config.json")
    client = TestClient(app)
    with client:
        headers = _login(client, "admin", "admin123")
        response = client.post(
            "/api/admin/model-setup/deepseek",
            headers=headers,
            json={"api_key": "sk-test-secret", "model": "deepseek-chat"},
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["llm"]["provider"] == "deepseek"
    assert "api_key" not in data["llm"]
    assert data["llm"]["api_key_set"] is True


def test_model_setup_configures_validated_local_llm(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_config, "RUNTIME_CONFIG_PATH", tmp_path / ".runtime_model_config.json")

    async def fake_validate_local_llm(base_url: str, model: str | None = None) -> dict:
        return {
            "status": "ok",
            "message": "LLM 服务验证通过",
            "model": model or "local-chat",
            "checked_at": "2026-06-09T00:00:00+00:00",
        }

    monkeypatch.setattr(runtime_config, "validate_local_llm", fake_validate_local_llm)
    client = TestClient(app)
    with client:
        headers = _login(client, "admin", "admin123")
        response = client.post(
            "/api/admin/model-setup/llm",
            headers=headers,
            json={"base_url": "http://127.0.0.1:18000/v1"},
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["llm"]["provider"] == "local_llm"
    assert data["llm"]["base_url"] == "http://127.0.0.1:18000/v1"
    assert data["llm"]["validation"]["status"] == "ok"


def test_model_setup_configures_validated_embedding_without_exposing_key(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_config, "RUNTIME_CONFIG_PATH", tmp_path / ".runtime_model_config.json")

    async def fake_validate_local_embedding(base_url: str, api_key: str = "", model: str | None = None) -> dict:
        return {
            "status": "ok",
            "message": "Embedding 服务验证通过",
            "model": model or "local-embed",
            "dim": 768,
            "checked_at": "2026-06-09T00:00:00+00:00",
        }

    monkeypatch.setattr(runtime_config, "validate_local_embedding", fake_validate_local_embedding)
    client = TestClient(app)
    with client:
        headers = _login(client, "admin", "admin123")
        response = client.post(
            "/api/admin/model-setup/embedding",
            headers=headers,
            json={"base_url": "http://127.0.0.1:19000/v1", "api_key": "emb-secret"},
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["embedding"]["provider"] == "local_embedding"
    assert data["embedding"]["dim"] == 768
    assert "api_key" not in data["embedding"]
    assert data["embedding"]["api_key_set"] is True


def test_admin_retrieval_test_endpoint_returns_trace_shape():
    client = TestClient(app)
    with client:
        headers = _login(client, "admin", "admin123")
        response = client.post(
            "/api/admin/retrieval/test",
            headers=headers,
            json={"query": "设备采购审批要求", "kb_id": None, "top_k": 3},
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["query"] == "设备采购审批要求"
    assert "evidence" in data
    assert "trace" in data
    assert {"vector", "keyword", "fused"}.issubset(data["trace"])
