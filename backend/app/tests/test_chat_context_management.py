import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.db.base import Base
from app.db.models import Conversation, ConversationMemory, Message, TempFile
from app.services.chat_context.context_manager import ChatContextManager
from app.services.rag import answer_service


def _db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    db = session_factory()
    return db


def _context_settings(**overrides) -> Settings:
    values = {
        "context_recent_turns": 2,
        "context_max_chars": 20000,
        "context_summary_trigger_messages": 6,
        "context_summary_target_chars": 3000,
        "context_uploaded_file_max_chars": 8000,
        "context_message_max_chars": 2000,
    }
    values.update(overrides)
    return Settings(**values)


def test_context_manager_builds_summary_recent_history_and_current_upload_context():
    db = _db_session()
    try:
        conversation = Conversation(title="上下文测试")
        db.add(conversation)
        db.flush()
        db.add(
            ConversationMemory(
                conversation_id=conversation.id,
                summary_text="历史摘要：用户之前关注预算执行率和合同付款节点。",
                token_estimate=32,
            )
        )
        old_message = Message(
            conversation_id=conversation.id,
            role="user",
            content="很早以前的问题不应原文进入上下文",
        )
        recent_user = Message(
            conversation_id=conversation.id,
            role="user",
            content="上一轮问：这份合同有哪些付款节点？",
        )
        recent_assistant = Message(
            conversation_id=conversation.id,
            role="assistant",
            content="上一轮答：合同有预付款和验收款。",
        )
        current_user = Message(
            conversation_id=conversation.id,
            role="user",
            content="请结合本轮文件回答金额是多少？",
        )
        db.add_all([old_message, recent_user, recent_assistant, current_user])
        db.flush()
        db.add(
            TempFile(
                conversation_id=conversation.id,
                file_name="旧附件.pdf",
                minio_object_key="temp-files/old.pdf",
                status="ready",
                parsed_text="旧附件正文，应该只作为历史附件摘要进入最近消息。",
                metadata_json={"used_message_id": recent_user.id},
            )
        )
        db.commit()

        manager = ChatContextManager(settings=_context_settings(context_recent_turns=1))
        messages = manager.build_messages(
            db,
            conversation_id=conversation.id,
            question=current_user.content,
            mode="file",
            evidence=[{"chunk_id": "c1", "file_name": "制度.pdf", "text": "采购金额超过 50 万元需审批。"}],
            uploaded_files=[
                {
                    "id": "upload-1",
                    "file_name": "本轮合同.pdf",
                    "text": "本轮合同显示合同金额为 88 万元，付款节点为验收后支付。",
                }
            ],
            current_message_id=current_user.id,
        )

        system_prompt = messages[0]["content"]
        assert messages[0]["role"] == "system"
        assert "历史摘要：用户之前关注预算执行率和合同付款节点。" in system_prompt
        assert "本轮合同.pdf" in system_prompt
        assert "合同金额为 88 万元" in system_prompt
        assert "采购金额超过 50 万元需审批" in system_prompt
        assert any(message["role"] == "user" and "上一轮问" in message["content"] for message in messages)
        assert any(message["role"] == "assistant" and "上一轮答" in message["content"] for message in messages)
        assert any("旧附件.pdf" in message["content"] for message in messages if message["role"] == "user")
        assert all("很早以前的问题不应原文进入上下文" not in message["content"] for message in messages[1:])
        assert messages[-1] == {"role": "user", "content": current_user.content}
    finally:
        db.close()


def test_context_manager_rolls_older_messages_into_conversation_memory():
    db = _db_session()
    try:
        conversation = Conversation(title="摘要测试")
        db.add(conversation)
        db.flush()
        for index in range(14):
            db.add(
                Message(
                    conversation_id=conversation.id,
                    role="user" if index % 2 == 0 else "assistant",
                    content=f"第{index}条历史内容，需要被压缩或保留。",
                )
            )
        db.commit()

        manager = ChatContextManager(settings=_context_settings(context_recent_turns=2))
        memory = manager.update_memory(db, conversation.id)

        assert memory is not None
        assert "第0条历史内容" in memory.summary_text
        assert "第9条历史内容" in memory.summary_text
        assert "第13条历史内容" not in memory.summary_text
        assert memory.summarized_until_message_id
        assert memory.token_estimate > 0
    finally:
        db.close()


@pytest.mark.asyncio
async def test_answer_service_sends_multi_message_context_to_llm(monkeypatch):
    db = _db_session()
    captured = {}

    async def fake_retrieve_evidence(db, question, kb_id=None, kb_ids=None, document_ids=None, current_user=None):
        return [{"chunk_id": "r1", "file_name": "制度库.pdf", "text": "制度库证据"}]

    class FakeLLMClient:
        async def chat(self, messages):
            captured["messages"] = messages
            return {"answer": "ok"}

    try:
        conversation = Conversation(title="回答服务上下文测试")
        db.add(conversation)
        db.flush()
        prior_user = Message(conversation_id=conversation.id, role="user", content="历史问题：合同金额是多少？")
        prior_assistant = Message(
            conversation_id=conversation.id,
            role="assistant",
            content="历史回答：合同金额是 88 万元。",
        )
        current_user = Message(conversation_id=conversation.id, role="user", content="那审批风险是什么？")
        db.add_all([prior_user, prior_assistant, current_user])
        db.commit()

        monkeypatch.setattr(answer_service, "retrieve_evidence", fake_retrieve_evidence)
        monkeypatch.setattr(answer_service, "get_llm_client", lambda: FakeLLMClient())

        result = await answer_service.answer_question(
            db,
            current_user.content,
            mode="risk",
            conversation_id=conversation.id,
            current_message_id=current_user.id,
            uploaded_files=[{"id": "f1", "file_name": "本轮附件.pdf", "text": "本轮附件说明金额为 88 万元。"}],
            settings=_context_settings(),
        )

        sent_messages = captured["messages"]
        assert result["answer"] == "ok"
        assert sent_messages[0]["role"] == "system"
        assert "本轮附件.pdf" in sent_messages[0]["content"]
        assert "制度库证据" in sent_messages[0]["content"]
        assert {"role": "user", "content": prior_user.content} in sent_messages
        assert {"role": "assistant", "content": prior_assistant.content} in sent_messages
        assert sent_messages[-1] == {"role": "user", "content": current_user.content}
    finally:
        db.close()
