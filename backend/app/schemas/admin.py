from pydantic import BaseModel


class AdminFilter(BaseModel):
    user_id: str | None = None
    action: str | None = None
    status: str | None = None


class UserCreate(BaseModel):
    username: str
    password: str
    display_name: str
    role: str = "auditor"
    department: str = "审计处"


class DeepSeekConfigRequest(BaseModel):
    api_key: str
    model: str = "deepseek-chat"


class LocalLLMConfigRequest(BaseModel):
    base_url: str
    model: str | None = None


class LocalEmbeddingConfigRequest(BaseModel):
    base_url: str
    api_key: str = ""
    model: str | None = None


class RetrievalTestRequest(BaseModel):
    query: str
    kb_id: str | None = None
    top_k: int = 8
