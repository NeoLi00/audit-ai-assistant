from typing import Protocol


class LLMClient(Protocol):
    async def chat(self, messages: list[dict], stream: bool = False) -> dict:
        ...


class EmbeddingClient(Protocol):
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...

