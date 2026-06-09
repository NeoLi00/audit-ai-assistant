from pydantic import BaseModel


class KnowledgeBaseCreate(BaseModel):
    name: str
    description: str = ""
    category: str | None = None
    visibility: str = "private"
