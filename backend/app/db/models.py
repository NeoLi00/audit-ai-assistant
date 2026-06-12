from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base


def now_utc() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid4())


def json_type():
    return JSON().with_variant(JSONB, "postgresql")


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(40), default="auditor", index=True)
    department: Mapped[str] = mapped_column(String(120), default="审计处")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class KnowledgeBase(Base, TimestampMixin):
    __tablename__ = "knowledge_bases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(120), index=True)
    visibility: Mapped[str] = mapped_column(String(40), default="department")
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    documents: Mapped[list["Document"]] = relationship(back_populates="knowledge_base")


class Document(Base, TimestampMixin):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    kb_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("knowledge_bases.id"), nullable=True)
    file_name: Mapped[str] = mapped_column(String(255), index=True)
    file_ext: Mapped[str] = mapped_column(String(20), index=True)
    mime_type: Mapped[str] = mapped_column(String(120), default="")
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    minio_bucket: Mapped[str] = mapped_column(String(120), default="")
    minio_object_key: Mapped[str] = mapped_column(String(500), default="")
    department_category: Mapped[str] = mapped_column(String(120), default="")
    business_type: Mapped[str] = mapped_column(String(120), default="")
    tags: Mapped[list[str]] = mapped_column(MutableList.as_mutable(json_type()), default=list)
    visibility: Mapped[str] = mapped_column(String(40), default="department")
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_current_version: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(40), default="uploaded", index=True)
    error_message: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[dict] = mapped_column(MutableDict.as_mutable(json_type()), default=dict)
    uploaded_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)

    knowledge_base: Mapped[KnowledgeBase | None] = relationship(back_populates="documents")
    blocks: Mapped[list["DocumentBlock"]] = relationship(
        cascade="all, delete-orphan", back_populates="document"
    )
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        cascade="all, delete-orphan", back_populates="document"
    )


class DocumentBlock(Base):
    __tablename__ = "document_blocks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id"), index=True)
    block_type: Mapped[str] = mapped_column(String(40), default="paragraph")
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sheet_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    heading_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    paragraph_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bbox_json: Mapped[dict | None] = mapped_column(json_type(), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    document: Mapped[Document] = relationship(back_populates="blocks")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id"), index=True)
    kb_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    block_ids: Mapped[list[str]] = mapped_column(MutableList.as_mutable(json_type()), default=list)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    parent_chunk_id: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    prev_chunk_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    next_chunk_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    chunk_type: Mapped[str] = mapped_column(String(40), default="paragraph", index=True)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    content_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    chunker_version: Mapped[str] = mapped_column(String(40), default="structured-v1")
    text: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(json_type(), default=dict)
    embedding_json: Mapped[list[float] | None] = mapped_column(json_type(), nullable=True)
    qdrant_point_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    opensearch_doc_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    document: Mapped[Document] = relationship(back_populates="chunks")


class Conversation(Base, TimestampMixin):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(200), default="新会话")
    mode: Mapped[str] = mapped_column(String(40), default="normal")
    metadata_json: Mapped[dict] = mapped_column(MutableDict.as_mutable(json_type()), default=dict)
    messages: Mapped[list["Message"]] = relationship(
        cascade="all, delete-orphan", back_populates="conversation"
    )
    temp_files: Mapped[list["TempFile"]] = relationship(
        cascade="all, delete-orphan", back_populates="conversation"
    )
    memory: Mapped["ConversationMemory | None"] = relationship(
        cascade="all, delete-orphan", back_populates="conversation", uselist=False
    )


class ConversationMemory(Base, TimestampMixin):
    __tablename__ = "conversation_memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id"), unique=True, index=True
    )
    summary_text: Mapped[str] = mapped_column(Text, default="")
    summarized_until_message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    summary_version: Mapped[int] = mapped_column(Integer, default=1)
    token_estimate: Mapped[int] = mapped_column(Integer, default=0)
    metadata_json: Mapped[dict] = mapped_column(json_type(), default=dict)

    conversation: Mapped[Conversation] = relationship(back_populates="memory")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(String(36), ForeignKey("conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(30))
    content: Mapped[str] = mapped_column(Text)
    citations_json: Mapped[list[dict]] = mapped_column(MutableList.as_mutable(json_type()), default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class TempFile(Base):
    __tablename__ = "temp_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(String(36), ForeignKey("conversations.id"), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    minio_object_key: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(40), default="uploaded")
    parsed_text: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[dict] = mapped_column(json_type(), default=dict)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    conversation: Mapped[Conversation] = relationship(back_populates="temp_files")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    target_type: Mapped[str] = mapped_column(String(80), default="")
    target_id: Mapped[str] = mapped_column(String(80), default="")
    ip_address: Mapped[str] = mapped_column(String(80), default="")
    user_agent: Mapped[str] = mapped_column(String(255), default="")
    detail_json: Mapped[dict] = mapped_column(json_type(), default=dict)
    status: Mapped[str] = mapped_column(String(40), default="success")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ModelCallLog(Base):
    __tablename__ = "model_call_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    provider: Mapped[str] = mapped_column(String(80))
    model_name: Mapped[str] = mapped_column(String(120), default="")
    endpoint_type: Mapped[str] = mapped_column(String(40))
    response_time_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(40), default="success")
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
