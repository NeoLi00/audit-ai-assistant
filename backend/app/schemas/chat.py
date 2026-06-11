from pydantic import BaseModel


class ConversationCreate(BaseModel):
    title: str | None = None
    mode: str = "normal"
    kb_ids: list[str] = []
    document_ids: list[str] = []
    scope_label: str | None = None
    client_request_id: str | None = None


class ChatMessageCreate(BaseModel):
    content: str
    kb_id: str | None = None
    kb_ids: list[str] = []
    document_ids: list[str] = []
    mode: str = "normal"


class ChatMessageUpdate(BaseModel):
    content: str
    kb_id: str | None = None
    kb_ids: list[str] = []
    document_ids: list[str] = []
    mode: str = "normal"


class ChatRegenerateRequest(BaseModel):
    kb_id: str | None = None
    kb_ids: list[str] = []
    document_ids: list[str] = []
    mode: str = "normal"


class ConversationUpdate(BaseModel):
    title: str


class FeedbackCreate(BaseModel):
    message_id: str
    feedback_type: str
    detail: str | None = None
