import pytest

from app.services.model_gateway import runtime_config


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self.payload


class FakeAsyncClient:
    requests: list[dict] = []
    fail_chat = False
    fail_embedding = False

    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def get(self, url: str, headers: dict | None = None):
        self.requests.append({"method": "GET", "url": url, "headers": headers or {}})
        return FakeResponse({"data": [{"id": "local-model"}]})

    async def post(self, url: str, json: dict, headers: dict | None = None):
        self.requests.append({"method": "POST", "url": url, "json": json, "headers": headers or {}})
        if url.endswith("/chat/completions"):
            if self.fail_chat:
                return FakeResponse({"error": "chat failed"}, status_code=500)
            return FakeResponse({"choices": [{"message": {"content": "ok"}}]})
        if url.endswith("/embeddings"):
            if self.fail_embedding:
                return FakeResponse({"data": []})
            return FakeResponse({"data": [{"embedding": [0.1, 0.2, 0.3]}]})
        return FakeResponse({}, status_code=404)


@pytest.mark.asyncio
async def test_configure_local_llm_validates_chat_completion_before_saving(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_config, "RUNTIME_CONFIG_PATH", tmp_path / ".runtime_model_config.json")
    FakeAsyncClient.requests = []
    FakeAsyncClient.fail_chat = False
    monkeypatch.setattr(runtime_config.httpx, "AsyncClient", FakeAsyncClient)

    config = await runtime_config.configure_local_llm("http://127.0.0.1:18000/v1")

    assert config["llm"]["provider"] == "local_llm"
    assert config["llm"]["base_url"] == "http://127.0.0.1:18000/v1"
    assert config["llm"]["model"] == "local-model"
    assert config["llm"]["validation"]["status"] == "ok"
    assert any(request["url"].endswith("/chat/completions") for request in FakeAsyncClient.requests)


@pytest.mark.asyncio
async def test_configure_local_llm_accepts_full_chat_endpoint_and_explicit_model(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_config, "RUNTIME_CONFIG_PATH", tmp_path / ".runtime_model_config.json")
    FakeAsyncClient.requests = []
    FakeAsyncClient.fail_chat = False
    monkeypatch.setattr(runtime_config.httpx, "AsyncClient", FakeAsyncClient)

    config = await runtime_config.configure_local_llm(
        "http://llm.local.test:1325/v1/chat/completions",
        model="local-chat-model",
    )

    assert config["llm"]["base_url"] == "http://llm.local.test:1325/v1"
    assert config["llm"]["model"] == "local-chat-model"
    post_request = next(request for request in FakeAsyncClient.requests if request["url"].endswith("/chat/completions"))
    assert post_request["url"] == "http://llm.local.test:1325/v1/chat/completions"
    assert post_request["json"]["model"] == "local-chat-model"
    assert post_request["json"]["messages"][0]["content"] == "回复一句：LLM 连接成功"


@pytest.mark.asyncio
async def test_configure_embedding_validates_vector_and_hides_api_key(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_config, "RUNTIME_CONFIG_PATH", tmp_path / ".runtime_model_config.json")
    FakeAsyncClient.requests = []
    FakeAsyncClient.fail_embedding = False
    monkeypatch.setattr(runtime_config.httpx, "AsyncClient", FakeAsyncClient)

    config = await runtime_config.configure_local_embedding("http://127.0.0.1:19000/v1", api_key="emb-secret")

    assert config["embedding"]["provider"] == "local_embedding"
    assert config["embedding"]["base_url"] == "http://127.0.0.1:19000/v1"
    assert config["embedding"]["model"] == "local-model"
    assert config["embedding"]["dim"] == 3
    assert config["embedding"]["api_key_set"] is True
    assert "api_key" not in config["embedding"]
    post_request = next(request for request in FakeAsyncClient.requests if request["url"].endswith("/embeddings"))
    assert post_request["headers"]["Authorization"] == "Bearer emb-secret"


@pytest.mark.asyncio
async def test_configure_embedding_accepts_root_embeddings_endpoint_with_key_and_model(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_config, "RUNTIME_CONFIG_PATH", tmp_path / ".runtime_model_config.json")
    FakeAsyncClient.requests = []
    FakeAsyncClient.fail_embedding = False
    monkeypatch.setattr(runtime_config.httpx, "AsyncClient", FakeAsyncClient)

    config = await runtime_config.configure_local_embedding(
        "http://embedding.local.test:5770/embeddings",
        api_key="dummy",
        model="local-embedding-model",
    )

    assert config["embedding"]["base_url"] == "http://embedding.local.test:5770"
    assert config["embedding"]["model"] == "local-embedding-model"
    post_request = next(request for request in FakeAsyncClient.requests if request["url"].endswith("/embeddings"))
    assert post_request["url"] == "http://embedding.local.test:5770/embeddings"
    assert post_request["headers"]["Authorization"] == "Bearer dummy"
    assert post_request["json"]["model"] == "local-embedding-model"
    assert post_request["json"]["input"] == "测试 embedding 是否可用"


@pytest.mark.asyncio
async def test_invalid_embedding_config_is_not_saved(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_config, "RUNTIME_CONFIG_PATH", tmp_path / ".runtime_model_config.json")
    FakeAsyncClient.requests = []
    FakeAsyncClient.fail_embedding = True
    monkeypatch.setattr(runtime_config.httpx, "AsyncClient", FakeAsyncClient)

    with pytest.raises(runtime_config.ModelValidationError):
        await runtime_config.configure_local_embedding("http://127.0.0.1:19000/v1")

    assert runtime_config.load_runtime_config()["embedding"] == {}
