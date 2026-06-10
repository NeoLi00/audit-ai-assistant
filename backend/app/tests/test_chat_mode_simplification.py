from fastapi.testclient import TestClient

from app.api.routes import chat as chat_routes
from app.db.models import Conversation
from app.db.session import SessionLocal
from app.main import app


def _login(client: TestClient) -> dict[str, str]:
    token = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["data"][
        "access_token"
    ]
    return {"Authorization": f"Bearer {token}"}


def _cleanup_conversation(conversation_id: str) -> None:
    with SessionLocal() as db:
        conversation = db.get(Conversation, conversation_id)
        if conversation:
            db.delete(conversation)
        db.commit()


def test_chat_routes_normalize_modes_to_plain_question_answering(monkeypatch):
    captured = {}

    async def fake_answer_question(
        db,
        question,
        kb_id=None,
        kb_ids=None,
        document_ids=None,
        mode="normal",
        uploaded_files=None,
        conversation_id=None,
        current_message_id=None,
        current_user=None,
    ):
        captured["mode"] = mode
        captured["kb_ids"] = kb_ids
        return {"answer": "普通问答回答", "citations": []}

    monkeypatch.setattr(chat_routes, "answer_question", fake_answer_question)
    client = TestClient(app, raise_server_exceptions=False)

    with client:
        headers = _login(client)
        created = client.post(
            "/api/chat/conversations",
            headers=headers,
            json={"title": "模式归一测试", "mode": "risk"},
        ).json()["data"]
        conversation_id = created["id"]
        response = client.post(
            f"/api/chat/conversations/{conversation_id}/messages",
            headers=headers,
            json={"content": "请回答这个问题", "mode": "policy", "kb_ids": ["kb-a", "kb-b"]},
        )

    try:
        assert created["mode"] == "normal"
        assert response.status_code == 200
        assert captured["mode"] == "normal"
        assert captured["kb_ids"] == ["kb-a", "kb-b"]
    finally:
        _cleanup_conversation(conversation_id)
