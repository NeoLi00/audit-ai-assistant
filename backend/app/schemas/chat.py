from pydantic import BaseModel


class ConversationCreate(BaseModel):
    title: str | None = None
    mode: str = "normal"


class ChatMessageCreate(BaseModel):
    content: str
    kb_id: str | None = None
    kb_ids: list[str] = []
    mode: str = "normal"


class FeedbackCreate(BaseModel):
    message_id: str
    feedback_type: str
    detail: str | None = None
