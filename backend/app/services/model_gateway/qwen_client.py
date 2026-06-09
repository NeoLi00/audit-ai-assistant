from dataclasses import dataclass
from time import perf_counter

import httpx

from app.core.config import Settings, get_settings


@dataclass
class QwenClient:
    settings: Settings | None = None

    async def chat(self, messages: list[dict], stream: bool = False) -> dict:
        settings = self.settings or get_settings()
        if not settings.llm_base_url:
            raise RuntimeError("LLM_BASE_URL is empty")
        payload = {"model": settings.llm_model, "messages": messages, "stream": stream}
        headers = {}
        if settings.llm_api_key:
            headers["Authorization"] = f"Bearer {settings.llm_api_key}"
        started = perf_counter()
        async with httpx.AsyncClient(timeout=settings.llm_timeout) as client:
            response = await client.post(
                f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
        elapsed_ms = int((perf_counter() - started) * 1000)
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return {
            "provider": settings.llm_provider,
            "model": settings.llm_model,
            "answer": content,
            "raw": data,
            "response_time_ms": elapsed_ms,
        }

