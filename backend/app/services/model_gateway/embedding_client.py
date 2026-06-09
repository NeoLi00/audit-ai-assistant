from dataclasses import dataclass

import httpx

from app.core.config import Settings, get_settings


@dataclass
class RemoteEmbeddingClient:
    settings: Settings | None = None

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        settings = self.settings or get_settings()
        if not settings.embed_base_url:
            raise RuntimeError("EMBED_BASE_URL is empty")
        headers = {}
        if settings.embed_api_key:
            headers["Authorization"] = f"Bearer {settings.embed_api_key}"
        embeddings: list[list[float]] = []
        async with httpx.AsyncClient(timeout=settings.embed_timeout) as client:
            for start in range(0, len(texts), settings.embed_batch_size):
                batch = texts[start : start + settings.embed_batch_size]
                try:
                    embeddings.extend(await self._request_embeddings(client, settings, headers, batch))
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code not in {400, 422}:
                        raise
                    for text in batch:
                        embeddings.extend(await self._request_embeddings(client, settings, headers, text))
        return embeddings

    async def _request_embeddings(
        self,
        client: httpx.AsyncClient,
        settings: Settings,
        headers: dict,
        input_value: str | list[str],
    ) -> list[list[float]]:
        response = await client.post(
            f"{settings.embed_base_url.rstrip('/')}/embeddings",
            json={"model": settings.embed_model, "input": input_value},
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()
        vectors = [item["embedding"] for item in data.get("data", [])]
        expected = 1 if isinstance(input_value, str) else len(input_value)
        if len(vectors) != expected:
            raise RuntimeError(f"Embedding 服务返回数量不匹配：expected={expected}, actual={len(vectors)}")
        return vectors
