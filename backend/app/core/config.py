from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "审计 AI 助手平台"
    app_env: str = "local"
    api_prefix: str = "/api"
    secret_key: str = "dev-secret-change-me"
    access_token_expire_minutes: int = 30
    auto_create_tables: bool = True
    process_documents_inline: bool = True

    database_url: str = "sqlite:///./audit_ai_local.db"
    redis_url: str = "redis://localhost:16379/0"
    celery_broker_url: str = "redis://localhost:16379/1"
    celery_result_backend: str = "redis://localhost:16379/2"

    minio_endpoint: str = "localhost:19000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin123"
    minio_bucket: str = "audit-documents"
    minio_secure: bool = False
    use_local_storage_fallback: bool = True
    local_storage_dir: Path = Path(".local_storage")

    qdrant_url: str = "http://localhost:16333"
    qdrant_collection: str = "audit_chunks"
    enable_opensearch: bool = False
    opensearch_url: str = "http://localhost:19200"

    llm_provider: str = "school_qwen"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = "qwen"
    llm_timeout: int = 120
    llm_stream: bool = True
    use_mock_llm: bool = True

    embed_provider: str = "school_embedding"
    embed_base_url: str = ""
    embed_api_key: str = ""
    embed_model: str = "school-embedding"
    embed_dim: int = 1024
    embed_batch_size: int = 16
    embed_timeout: int = 60
    use_mock_embedding: bool = True

    document_parser_provider: str = "mineru"
    mineru_command: str = "mineru"
    mineru_backend: str = "pipeline"
    mineru_output_dir: Path = Path(".local_storage/mineru-output")
    mineru_timeout: int = 300

    local_e5_model: str = "intfloat/multilingual-e5-small"
    local_e5_base_url: str = "http://127.0.0.1:18080/v1"
    local_e5_host: str = "127.0.0.1"
    local_e5_port: int = 18080

    max_upload_mb: int = 300
    temp_file_ttl_hours: int = 24
    context_recent_turns: int = 6
    context_max_chars: int = 24000
    context_summary_trigger_messages: int = 12
    context_summary_target_chars: int = 3000
    context_uploaded_file_max_chars: int = 12000
    context_message_max_chars: int = 4000

    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
