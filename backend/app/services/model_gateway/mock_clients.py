import hashlib
import math
from dataclasses import dataclass

from app.core.config import Settings, get_settings


@dataclass
class MockLLMClient:
    settings: Settings | None = None

    async def chat(self, messages: list[dict], stream: bool = False) -> dict:
        user_message = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        answer = (
            "这是 mock 模型返回。系统已接收到你的问题，并会在真实模型启用后结合会话上下文、"
            "本轮上传文件和检索到的知识库材料自然回答。"
        )
        return {
            "provider": "mock",
            "model": (self.settings or get_settings()).llm_model,
            "answer": answer,
            "raw": {"question_excerpt": user_message[:120], "stream": stream},
        }


@dataclass
class MockEmbeddingClient:
    settings: Settings | None = None

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        settings = self.settings or get_settings()
        return [self._embed(text, settings.embed_dim) for text in texts]

    def _embed(self, text: str, dim: int) -> list[float]:
        seed = hashlib.sha256(text.encode("utf-8")).digest()
        values: list[float] = []
        counter = 0
        while len(values) < dim:
            block = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
            for i in range(0, len(block), 4):
                raw = int.from_bytes(block[i : i + 4], "big")
                values.append((raw / 2**32) * 2 - 1)
                if len(values) == dim:
                    break
            counter += 1
        norm = math.sqrt(sum(v * v for v in values)) or 1.0
        return [v / norm for v in values]
