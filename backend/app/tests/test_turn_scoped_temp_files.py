from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.api.routes import chat as chat_routes
from app.db.models import Conversation, TempFile
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


def test_ready_temp_file_is_bound_to_single_user_turn_and_sent_to_prompt(monkeypatch):
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
        captured["uploaded_files"] = uploaded_files
        return {"answer": "已根据本轮上传文件回答", "citations": []}

    monkeypatch.setattr(chat_routes, "answer_question", fake_answer_question)
    client = TestClient(app, raise_server_exceptions=False)

    with client:
        headers = _login(client)
        conversation = client.post("/api/chat/conversations", headers=headers, json={"title": "turn-file-test"}).json()[
            "data"
        ]
        conversation_id = conversation["id"]
        with SessionLocal() as db:
            db.add(
                TempFile(
                    conversation_id=conversation_id,
                    file_name="本轮文件.pdf",
                    minio_object_key="temp-files/turn-file.pdf",
                    status="ready",
                    parsed_text="本文件说明采购合同金额为 120 万元，需要复核招标审批。",
                    metadata_json={"local_path": "temp-files/turn-file.pdf"},
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                )
            )
            db.commit()

        response = client.post(
            f"/api/chat/conversations/{conversation_id}/messages",
            headers=headers,
            json={"content": "这个文件的金额是多少？", "mode": "file"},
        )
        detail = client.get(f"/api/chat/conversations/{conversation_id}", headers=headers).json()["data"]

    try:
        assert response.status_code == 200
        assert captured["uploaded_files"][0]["file_name"] == "本轮文件.pdf"
        assert "120 万元" in captured["uploaded_files"][0]["text"]
        assert detail["temp_files"] == []
        user_messages = [message for message in detail["messages"] if message["role"] == "user"]
        assert user_messages[-1]["attachments"][0]["file_name"] == "本轮文件.pdf"
    finally:
        _cleanup_conversation(conversation_id)


def test_message_is_rejected_while_temp_file_is_still_parsing():
    client = TestClient(app, raise_server_exceptions=False)

    with client:
        headers = _login(client)
        conversation = client.post(
            "/api/chat/conversations",
            headers=headers,
            json={"title": "parsing-file-test"},
        ).json()["data"]
        conversation_id = conversation["id"]
        with SessionLocal() as db:
            db.add(
                TempFile(
                    conversation_id=conversation_id,
                    file_name="解析中文件.pdf",
                    minio_object_key="temp-files/parsing-file.pdf",
                    status="parsing",
                    metadata_json={"local_path": "temp-files/parsing-file.pdf"},
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                )
            )
            db.commit()
        response = client.post(
            f"/api/chat/conversations/{conversation_id}/messages",
            headers=headers,
            json={"content": "请解读这个文件", "mode": "file"},
        )

    try:
        assert response.status_code == 400
        assert "仍在解析" in response.json()["detail"]
    finally:
        _cleanup_conversation(conversation_id)
