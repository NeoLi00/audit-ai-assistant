from app.core.config import Settings, get_settings
from app.services.model_gateway.embedding_client import RemoteEmbeddingClient
from app.services.model_gateway.mock_clients import MockEmbeddingClient, MockLLMClient
from app.services.model_gateway.qwen_client import QwenClient
from app.services.model_gateway.runtime_config import settings_with_runtime


def get_llm_client(settings: Settings | None = None):
    settings = settings_with_runtime(settings or get_settings())
    if settings.use_mock_llm or not settings.llm_base_url:
        return MockLLMClient(settings=settings)
    return QwenClient(settings=settings)


def get_embedding_client(settings: Settings | None = None):
    settings = settings_with_runtime(settings or get_settings())
    if settings.use_mock_embedding or not settings.embed_base_url:
        return MockEmbeddingClient(settings=settings)
    return RemoteEmbeddingClient(settings=settings)
