import pytest

from app.core.config import Settings
from app.services.model_gateway.mock_clients import MockEmbeddingClient


@pytest.mark.asyncio
async def test_mock_embedding_is_deterministic_and_uses_configured_dimension():
    settings = Settings(embed_dim=32, use_mock_embedding=True)
    client = MockEmbeddingClient(settings=settings)

    first = await client.embed_texts(["设备采购制度", "合同付款条款"])
    second = await client.embed_texts(["设备采购制度", "合同付款条款"])

    assert first == second
    assert len(first) == 2
    assert len(first[0]) == 32
    assert first[0] != first[1]

