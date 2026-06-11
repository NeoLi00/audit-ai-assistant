from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.api.routes import chat as chat_routes
from app.db.models import Conversation, TempFile
from app.db.session import SessionLocal
from app.main import app


def _login(client: TestClient, username: str = "admin", password: str = "admin123") -> dict[str, str]:
    token = client.post("/api/auth/login", json={"username": username, "password": password}).json()["data"][
        "access_token"
    ]
    return {"Authorization": f"Bearer {token}"}


def _cleanup_conversation(conversation_id: str) -> None:
    with SessionLocal() as db:
        conversation = db.get(Conversation, conversation_id)
        if conversation:
            db.delete(conversation)
        db.commit()


def test_first_user_message_generates_short_conversation_title(monkeypatch):
    async def fake_answer_question(*args, **kwargs):
        return {"answer": "合同付款条件存在逾期和审批缺失风险。", "citations": []}

    class FakeTitleClient:
        async def chat(self, messages):
            return {"answer": "合同付款风险分析"}

    monkeypatch.setattr(chat_routes, "answer_question", fake_answer_question)
    monkeypatch.setattr(chat_routes, "get_llm_client", lambda: FakeTitleClient())
    client = TestClient(app, raise_server_exceptions=False)

    with client:
        headers = _login(client)
        conversation = client.post("/api/chat/conversations", headers=headers, json={"title": "新会话"}).json()["data"]
        conversation_id = conversation["id"]
        response = client.post(
            f"/api/chat/conversations/{conversation_id}/messages",
            headers=headers,
            json={"content": "请总结这个合同的付款条件和审计风险"},
        )
        detail = client.get(f"/api/chat/conversations/{conversation_id}", headers=headers).json()["data"]

    try:
        assert response.status_code == 200
        assert detail["title"] == "合同付款风险分析"
    finally:
        _cleanup_conversation(conversation_id)


def test_conversations_can_be_searched_by_title_or_message_content(monkeypatch):
    async def fake_answer_question(*args, **kwargs):
        return {"answer": "这份材料讨论 IMAP 连接超时排查。", "citations": []}

    class FakeTitleClient:
        async def chat(self, messages):
            return {"answer": "邮箱连接排查"}

    monkeypatch.setattr(chat_routes, "answer_question", fake_answer_question)
    monkeypatch.setattr(chat_routes, "get_llm_client", lambda: FakeTitleClient())
    client = TestClient(app, raise_server_exceptions=False)

    with client:
        headers = _login(client)
        conversation = client.post("/api/chat/conversations", headers=headers, json={"title": "新会话"}).json()["data"]
        conversation_id = conversation["id"]
        client.post(
            f"/api/chat/conversations/{conversation_id}/messages",
            headers=headers,
            json={"content": "帮我排查 IMAP idle timeout 的原因"},
        )
        by_title = client.get("/api/chat/conversations", headers=headers, params={"q": "邮箱连接"}).json()["data"]
        by_message = client.get("/api/chat/conversations", headers=headers, params={"q": "idle timeout"}).json()["data"]
        by_keywords = client.get("/api/chat/conversations", headers=headers, params={"q": "IMAP timeout"}).json()[
            "data"
        ]

    try:
        assert any(item["id"] == conversation_id for item in by_title)
        assert any(item["id"] == conversation_id for item in by_message)
        assert any(item["id"] == conversation_id for item in by_keywords)
        title_match = next(item for item in by_title if item["id"] == conversation_id)["search_match"]
        message_match = next(item for item in by_message if item["id"] == conversation_id)["search_match"]
        keyword_match = next(item for item in by_keywords if item["id"] == conversation_id)["search_match"]
        assert title_match["source"] == "title"
        assert title_match["snippet"] == "邮箱连接排查"
        assert title_match["matched_text"] == "邮箱连接"
        assert message_match["source"] == "message"
        assert "idle timeout" in message_match["snippet"]
        assert message_match["matched_text"] == "idle timeout"
        assert keyword_match["source"] == "message"
        assert keyword_match["matched_text"] == "IMAP"
    finally:
        _cleanup_conversation(conversation_id)


def test_scoped_conversation_create_is_idempotent_for_same_client_request():
    client = TestClient(app, raise_server_exceptions=False)

    with client:
        headers = _login(client)
        first = client.post(
            "/api/chat/conversations",
            headers=headers,
            json={
                "title": "围绕制度库",
                "kb_ids": ["kb-1"],
                "scope_label": "制度库",
                "client_request_id": "kb-launch-1",
            },
        )
        second = client.post(
            "/api/chat/conversations",
            headers=headers,
            json={
                "title": "围绕制度库",
                "kb_ids": ["kb-1"],
                "scope_label": "制度库",
                "client_request_id": "kb-launch-1",
            },
        )
        conversations = client.get("/api/chat/conversations", headers=headers).json()["data"]

    conversation_id = first.json()["data"]["id"]
    try:
        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()["data"]["id"] == conversation_id
        assert sum(1 for item in conversations if item["id"] == conversation_id) == 1
    finally:
        _cleanup_conversation(conversation_id)


def test_conversation_title_can_be_updated_and_conversation_can_be_deleted(monkeypatch):
    removed_keys: list[str] = []
    monkeypatch.setattr(chat_routes.ObjectStorage, "remove", lambda self, key: removed_keys.append(key))
    client = TestClient(app, raise_server_exceptions=False)

    with client:
        headers = _login(client)
        conversation = client.post(
            "/api/chat/conversations",
            headers=headers,
            json={"title": "原始标题"},
        ).json()["data"]
        conversation_id = conversation["id"]
        with SessionLocal() as db:
            db.add(
                TempFile(
                    conversation_id=conversation_id,
                    file_name="待清理.pdf",
                    minio_object_key="temp-files/delete-conversation.pdf",
                    status="ready",
                    parsed_text="待清理内容",
                    metadata_json={"local_path": "temp-files/delete-conversation.pdf"},
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                )
            )
            db.commit()

        renamed = client.patch(
            f"/api/chat/conversations/{conversation_id}",
            headers=headers,
            json={"title": "专项合同复核"},
        )
        deleted = client.delete(f"/api/chat/conversations/{conversation_id}", headers=headers)
        missing = client.get(f"/api/chat/conversations/{conversation_id}", headers=headers)

    assert renamed.status_code == 200
    assert renamed.json()["data"]["title"] == "专项合同复核"
    assert deleted.status_code == 200
    assert deleted.json()["data"]["deleted"] == conversation_id
    assert missing.status_code == 404
    assert removed_keys == ["temp-files/delete-conversation.pdf"]


def test_pending_temp_file_can_be_deleted_before_it_is_sent(monkeypatch):
    removed_keys: list[str] = []
    monkeypatch.setattr(chat_routes.ObjectStorage, "remove", lambda self, key: removed_keys.append(key))
    client = TestClient(app, raise_server_exceptions=False)

    with client:
        headers = _login(client)
        conversation = client.post(
            "/api/chat/conversations",
            headers=headers,
            json={"title": "附件删除"},
        ).json()["data"]
        conversation_id = conversation["id"]
        with SessionLocal() as db:
            temp_file = TempFile(
                conversation_id=conversation_id,
                file_name="未发送附件.pdf",
                minio_object_key="temp-files/pending-delete.pdf",
                status="ready",
                parsed_text="待删除",
                metadata_json={"local_path": "temp-files/pending-delete.pdf"},
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
            db.add(temp_file)
            db.flush()
            temp_file_id = temp_file.id
            db.commit()

        response = client.delete(
            f"/api/chat/conversations/{conversation_id}/temp-files/{temp_file_id}",
            headers=headers,
        )
        detail = client.get(f"/api/chat/conversations/{conversation_id}", headers=headers).json()["data"]

    try:
        assert response.status_code == 200
        assert response.json()["data"]["deleted"] == temp_file_id
        assert detail["temp_files"] == []
        assert removed_keys == ["temp-files/pending-delete.pdf"]
    finally:
        _cleanup_conversation(conversation_id)


def test_sent_temp_file_cannot_be_deleted_from_history(monkeypatch):
    monkeypatch.setattr(chat_routes.ObjectStorage, "remove", lambda self, key: None)
    client = TestClient(app, raise_server_exceptions=False)

    with client:
        headers = _login(client)
        conversation = client.post(
            "/api/chat/conversations",
            headers=headers,
            json={"title": "历史附件"},
        ).json()["data"]
        conversation_id = conversation["id"]
        with SessionLocal() as db:
            temp_file = TempFile(
                conversation_id=conversation_id,
                file_name="历史附件.pdf",
                minio_object_key="temp-files/history.pdf",
                status="ready",
                parsed_text="历史",
                metadata_json={"used_message_id": "message-1", "local_path": "temp-files/history.pdf"},
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
            db.add(temp_file)
            db.flush()
            temp_file_id = temp_file.id
            db.commit()

        response = client.delete(
            f"/api/chat/conversations/{conversation_id}/temp-files/{temp_file_id}",
            headers=headers,
        )

    try:
        assert response.status_code == 400
        assert "已发送" in response.json()["detail"]
    finally:
        _cleanup_conversation(conversation_id)


def test_conversation_scope_document_ids_are_passed_to_answer_service(monkeypatch):
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
        captured["kb_ids"] = kb_ids
        captured["document_ids"] = document_ids
        return {"answer": "围绕文件回答", "citations": []}

    monkeypatch.setattr(chat_routes, "answer_question", fake_answer_question)
    client = TestClient(app, raise_server_exceptions=False)

    with client:
        headers = _login(client)
        conversation = client.post(
            "/api/chat/conversations",
            headers=headers,
            json={
                "title": "围绕文件",
                "kb_ids": ["kb-1"],
                "document_ids": ["doc-1"],
                "scope_label": "制度.pdf",
            },
        ).json()["data"]
        conversation_id = conversation["id"]
        response = client.post(
            f"/api/chat/conversations/{conversation_id}/messages",
            headers=headers,
            json={"content": "只看这个文件回答"},
        )

    try:
        assert response.status_code == 200
        assert captured["kb_ids"] == ["kb-1"]
        assert captured["document_ids"] == ["doc-1"]
    finally:
        _cleanup_conversation(conversation_id)


def test_empty_document_ids_do_not_filter_out_knowledge_base_retrieval(monkeypatch):
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
        captured["kb_ids"] = kb_ids
        captured["document_ids"] = document_ids
        return {"answer": "知识库回答", "citations": [{"chunk_id": "c1"}]}

    monkeypatch.setattr(chat_routes, "answer_question", fake_answer_question)
    client = TestClient(app, raise_server_exceptions=False)

    with client:
        headers = _login(client)
        conversation = client.post(
            "/api/chat/conversations",
            headers=headers,
            json={"title": "围绕知识库", "kb_ids": ["kb-1"], "scope_label": "制度库"},
        ).json()["data"]
        conversation_id = conversation["id"]
        response = client.post(
            f"/api/chat/conversations/{conversation_id}/messages",
            headers=headers,
            json={"content": "只看知识库回答", "kb_ids": ["kb-1"]},
        )

    try:
        assert response.status_code == 200
        assert captured["kb_ids"] == ["kb-1"]
        assert captured["document_ids"] is None
        assert len(response.json()["data"]["message"]["citations"]) == 1
    finally:
        _cleanup_conversation(conversation_id)


def test_assistant_message_can_be_regenerated_without_duplicating_user_message(monkeypatch):
    answers = iter(["第一次回答", "重新生成回答"])
    captured_kb_ids: list[list[str] | None] = []

    async def fake_answer_question(*args, **kwargs):
        captured_kb_ids.append(kwargs.get("kb_ids"))
        return {"answer": next(answers), "citations": []}

    monkeypatch.setattr(chat_routes, "answer_question", fake_answer_question)
    client = TestClient(app, raise_server_exceptions=False)

    with client:
        headers = _login(client)
        conversation = client.post("/api/chat/conversations", headers=headers, json={"title": "重生测试"}).json()[
            "data"
        ]
        conversation_id = conversation["id"]
        first = client.post(
            f"/api/chat/conversations/{conversation_id}/messages",
            headers=headers,
            json={"content": "重新生成这轮", "kb_ids": ["kb-old"]},
        ).json()["data"]
        assistant_id = first["message"]["id"]

        regenerated = client.post(
            f"/api/chat/conversations/{conversation_id}/messages/{assistant_id}/regenerate",
            headers=headers,
            json={"kb_ids": ["kb-new"]},
        )
        messages = regenerated.json()["data"]["messages"]

    try:
        assert regenerated.status_code == 200
        assert [message["role"] for message in messages] == ["user", "assistant"]
        assert messages[0]["content"] == "重新生成这轮"
        assert messages[1]["content"] == "重新生成回答"
        assert messages[1]["id"] != assistant_id
        assert captured_kb_ids == [["kb-old"], ["kb-new"]]
    finally:
        _cleanup_conversation(conversation_id)


def test_editing_user_message_prunes_later_turns_and_reruns_answer(monkeypatch):
    answers = iter(["第一轮旧回答", "第二轮旧回答", "第一轮新回答"])

    async def fake_answer_question(*args, **kwargs):
        return {"answer": next(answers), "citations": []}

    monkeypatch.setattr(chat_routes, "answer_question", fake_answer_question)
    client = TestClient(app, raise_server_exceptions=False)

    with client:
        headers = _login(client)
        conversation = client.post("/api/chat/conversations", headers=headers, json={"title": "编辑测试"}).json()[
            "data"
        ]
        conversation_id = conversation["id"]
        first = client.post(
            f"/api/chat/conversations/{conversation_id}/messages",
            headers=headers,
            json={"content": "旧问题"},
        ).json()["data"]
        user_id = first["user_message"]["id"]
        client.post(
            f"/api/chat/conversations/{conversation_id}/messages",
            headers=headers,
            json={"content": "后续问题"},
        )

        edited = client.patch(
            f"/api/chat/conversations/{conversation_id}/messages/{user_id}",
            headers=headers,
            json={"content": "新问题"},
        )
        messages = edited.json()["data"]["messages"]

    try:
        assert edited.status_code == 200
        assert [message["role"] for message in messages] == ["user", "assistant"]
        assert messages[0]["id"] == user_id
        assert messages[0]["content"] == "新问题"
        assert messages[1]["content"] == "第一轮新回答"
    finally:
        _cleanup_conversation(conversation_id)
