from pathlib import Path

from fastapi.testclient import TestClient
from starlette.background import BackgroundTasks

from app.db.models import Conversation, Document, DocumentBlock, DocumentChunk
from app.db.session import SessionLocal
from app.main import app


def _login(client: TestClient, username: str = "admin", password: str = "admin123") -> dict[str, str]:
    token = client.post("/api/auth/login", json={"username": username, "password": password}).json()["data"][
        "access_token"
    ]
    return {"Authorization": f"Bearer {token}"}


def _noop_background_tasks(monkeypatch) -> list[tuple]:
    calls = []

    def add_task(self, func, *args, **kwargs):
        calls.append((func, args, kwargs))

    monkeypatch.setattr(BackgroundTasks, "add_task", add_task)
    return calls


def _delete_document(document_id: str) -> None:
    with SessionLocal() as db:
        db.query(DocumentBlock).filter(DocumentBlock.document_id == document_id).delete()
        db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete()
        document = db.get(Document, document_id)
        if document:
            db.delete(document)
        db.commit()


def _delete_conversation(conversation_id: str) -> None:
    with SessionLocal() as db:
        conversation = db.get(Conversation, conversation_id)
        if conversation:
            db.delete(conversation)
        db.commit()


def test_knowledge_base_upload_returns_before_document_processing(monkeypatch, tmp_path: Path):
    calls = _noop_background_tasks(monkeypatch)
    client = TestClient(app, raise_server_exceptions=False)
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%fake")

    with client:
        headers = _login(client)
        kb = client.get("/api/kb", headers=headers).json()["data"][0]
        response = client.post(
            "/api/documents/upload",
            headers=headers,
            data={"kb_id": kb["id"], "department_category": "个人知识库", "business_type": "制度依据"},
            files={"file": ("sample.pdf", pdf.read_bytes(), "application/pdf")},
        )

    assert response.status_code == 200
    assert response.json()["data"]["status"] in {"uploaded", "parsing"}
    assert calls
    _delete_document(response.json()["data"]["id"])


def test_temp_upload_returns_before_mineru_processing(monkeypatch, tmp_path: Path):
    calls = _noop_background_tasks(monkeypatch)
    client = TestClient(app, raise_server_exceptions=False)
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%fake")

    with client:
        headers = _login(client)
        conversation = client.post("/api/chat/conversations", headers=headers, json={"title": "上传测试"}).json()[
            "data"
        ]
        response = client.post(
            f"/api/chat/conversations/{conversation['id']}/temp-files",
            headers=headers,
            files={"file": ("sample.pdf", pdf.read_bytes(), "application/pdf")},
        )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "parsing"
    assert calls
    _delete_conversation(conversation["id"])
