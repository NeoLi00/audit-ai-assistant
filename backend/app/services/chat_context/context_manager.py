from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import ConversationMemory, Message, TempFile
from app.services.chat_context.summarizer import ConversationSummarizer
from app.services.chat_context.token_budget import enforce_context_budget, truncate_text
from app.services.rag.prompt_builder import build_audit_prompt


@dataclass
class ChatContextManager:
    settings: Settings | None = None

    def build_messages(
        self,
        db: Session,
        conversation_id: str | None,
        question: str,
        mode: str,
        evidence: list[dict],
        uploaded_files: list[dict] | None = None,
        current_message_id: str | None = None,
    ) -> list[dict]:
        settings = self.settings or get_settings()
        memory_summary = ""
        history_messages: list[dict] = []

        if conversation_id:
            memory = self._get_memory(db, conversation_id)
            memory_summary = memory.summary_text if memory else ""
            recent_messages = self._recent_messages(db, conversation_id, current_message_id)
            attachments_by_message = self._attachments_by_message(db, conversation_id)
            history_messages = [
                self._history_message(message, attachments_by_message.get(message.id, []))
                for message in recent_messages
                if message.role in {"user", "assistant"}
            ]

        system_prompt = build_audit_prompt(
            question,
            evidence,
            mode=mode,
            uploaded_files=uploaded_files,
            conversation_summary=memory_summary,
            uploaded_file_max_chars=settings.context_uploaded_file_max_chars,
        )
        messages = [
            {"role": "system", "content": system_prompt},
            *history_messages,
            {"role": "user", "content": truncate_text(question, settings.context_message_max_chars)},
        ]
        return enforce_context_budget(messages, settings.context_max_chars)

    def update_memory(self, db: Session, conversation_id: str) -> ConversationMemory | None:
        settings = self.settings or get_settings()
        all_messages = (
            db.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc(), Message.id.asc())
            .all()
        )
        if len(all_messages) <= settings.context_summary_trigger_messages:
            return self._get_memory(db, conversation_id)

        recent_limit = max(1, settings.context_recent_turns * 2)
        summarizable_messages = all_messages[:-recent_limit]
        if not summarizable_messages:
            return self._get_memory(db, conversation_id)

        memory = self._get_memory(db, conversation_id)
        if not memory:
            memory = ConversationMemory(conversation_id=conversation_id)
            db.add(memory)
            db.flush()

        new_messages = self._messages_after_previous_summary(summarizable_messages, memory.summarized_until_message_id)
        if not new_messages:
            return memory

        attachments_by_message = self._attachments_by_message(db, conversation_id)
        summary, token_estimate = ConversationSummarizer(settings).summarize(
            memory.summary_text,
            new_messages,
            attachments_by_message,
        )
        memory.summary_text = summary
        memory.summarized_until_message_id = new_messages[-1].id
        memory.token_estimate = token_estimate
        db.add(memory)
        db.commit()
        db.refresh(memory)
        return memory

    def _get_memory(self, db: Session, conversation_id: str) -> ConversationMemory | None:
        return db.query(ConversationMemory).filter(ConversationMemory.conversation_id == conversation_id).one_or_none()

    def _recent_messages(self, db: Session, conversation_id: str, current_message_id: str | None) -> list[Message]:
        settings = self.settings or get_settings()
        messages = (
            db.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc(), Message.id.asc())
            .all()
        )
        if current_message_id:
            messages = [message for message in messages if message.id != current_message_id]
        return messages[-(settings.context_recent_turns * 2) :]

    def _attachments_by_message(self, db: Session, conversation_id: str) -> dict[str, list[TempFile]]:
        attachments_by_message: dict[str, list[TempFile]] = {}
        temp_files = (
            db.query(TempFile)
            .filter(TempFile.conversation_id == conversation_id)
            .order_by(TempFile.created_at)
            .all()
        )
        for temp_file in temp_files:
            used_message_id = (temp_file.metadata_json or {}).get("used_message_id")
            if used_message_id:
                attachments_by_message.setdefault(used_message_id, []).append(temp_file)
        return attachments_by_message

    def _history_message(self, message: Message, attachments: list[TempFile]) -> dict:
        settings = self.settings or get_settings()
        content = truncate_text(message.content.strip(), settings.context_message_max_chars)
        attachment_lines = [self._format_historical_attachment(attachment) for attachment in attachments]
        if attachment_lines:
            content = f"{content}\n\n[历史附件摘要]\n" + "\n".join(attachment_lines)
        return {"role": message.role, "content": content}

    def _format_historical_attachment(self, attachment: TempFile) -> str:
        text = " ".join((attachment.parsed_text or "").split())
        if text:
            text = truncate_text(text, 600)
        else:
            text = f"状态={attachment.status}"
        return f"- {attachment.file_name}: {text}"

    def _messages_after_previous_summary(
        self,
        summarizable_messages: list[Message],
        summarized_until_message_id: str | None,
    ) -> list[Message]:
        if not summarized_until_message_id:
            return summarizable_messages
        for index, message in enumerate(summarizable_messages):
            if message.id == summarized_until_message_id:
                return summarizable_messages[index + 1 :]
        return summarizable_messages
