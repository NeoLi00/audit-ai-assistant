from dataclasses import dataclass

from app.core.config import Settings, get_settings
from app.db.models import Message, TempFile
from app.services.chat_context.token_budget import estimate_tokens, truncate_text

ROLE_NAMES = {
    "user": "用户",
    "assistant": "助手",
    "system": "系统",
}


@dataclass
class ConversationSummarizer:
    settings: Settings | None = None

    def summarize(
        self,
        existing_summary: str,
        messages: list[Message],
        attachments_by_message: dict[str, list[TempFile]],
    ) -> tuple[str, int]:
        settings = self.settings or get_settings()
        sections = []
        if existing_summary.strip():
            sections.append(existing_summary.strip())
        sections.append("【新增历史压缩】")
        for message in messages:
            role_name = ROLE_NAMES.get(message.role, message.role)
            content = _single_line(truncate_text(message.content.strip(), 700))
            sections.append(f"- {role_name}: {content}")
            for attachment in attachments_by_message.get(message.id, []):
                sections.append(f"  - 历史附件: {_attachment_summary(attachment)}")
        summary = "\n".join(section for section in sections if section)
        summary = _keep_tail(summary, settings.context_summary_target_chars)
        return summary, estimate_tokens(summary)


def _single_line(text: str) -> str:
    return " ".join(text.split())


def _attachment_summary(attachment: TempFile) -> str:
    text = _single_line(attachment.parsed_text or "")
    if text:
        text = truncate_text(text, 500)
    else:
        text = f"状态={attachment.status}"
    return f"{attachment.file_name}: {text}"


def _keep_tail(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    marker = "【较早摘要已压缩截断】\n"
    if max_chars <= len(marker):
        return text[-max_chars:]
    return f"{marker}{text[-(max_chars - len(marker)) :]}"

