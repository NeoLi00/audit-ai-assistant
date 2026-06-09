import httpx
import pytest

from app.core.config import Settings
from app.services.model_gateway import embedding_client
from app.services.model_gateway.embedding_client import RemoteEmbeddingClient


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("POST", "http://embedding.test/embeddings")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError(f"HTTP {self.status_code}", request=request, response=response)

    def json(self) -> dict:
        return self.payload


class FakeAsyncClient:
    calls: list[dict] = []

    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, url: str, json: dict, headers: dict | None = None):
        self.calls.append({"url": url, "json": json, "headers": headers or {}})
        if isinstance(json["input"], list):
            return FakeResponse({"error": "list input unsupported"}, status_code=400)
        return FakeResponse({"data": [{"embedding": [1.0, 2.0]}]})


@pytest.mark.asyncio
async def test_remote_embedding_client_falls_back_to_single_string_inputs(monkeypatch):
    FakeAsyncClient.calls = []
    monkeypatch.setattr(embedding_client.httpx, "AsyncClient", FakeAsyncClient)
    settings = Settings(
        embed_base_url="http://embedding.local.test:5770",
        embed_api_key="dummy",
        embed_model="local-embedding-model",
        embed_batch_size=2,
    )

    vectors = await RemoteEmbeddingClient(settings=settings).embed_texts(["材料一", "材料二"])

    assert vectors == [[1.0, 2.0], [1.0, 2.0]]
    assert FakeAsyncClient.calls[0]["json"]["input"] == ["材料一", "材料二"]
    assert FakeAsyncClient.calls[1]["json"]["input"] == "材料一"
    assert FakeAsyncClient.calls[2]["json"]["input"] == "材料二"
    assert all(call["json"]["model"] == "local-embedding-model" for call in FakeAsyncClient.calls)
    assert all(call["headers"]["Authorization"] == "Bearer dummy" for call in FakeAsyncClient.calls)
