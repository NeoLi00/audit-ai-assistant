import json
from datetime import UTC, datetime
from numbers import Real
from pathlib import Path
from threading import RLock
from urllib.parse import urlparse, urlunparse

import httpx

from app.core.config import Settings, get_settings

RUNTIME_CONFIG_PATH = Path(".runtime_model_config.json")
_lock = RLock()


class ModelValidationError(RuntimeError):
    pass


def _default_config() -> dict:
    return {"llm": {}, "embedding": {}, "local_e5": {"status": "stopped", "message": ""}}


def load_runtime_config() -> dict:
    with _lock:
        if not RUNTIME_CONFIG_PATH.exists():
            return _default_config()
        try:
            data = json.loads(RUNTIME_CONFIG_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return _default_config()
        merged = _default_config()
        merged.update(data)
        return merged


def save_runtime_config(config: dict) -> dict:
    with _lock:
        RUNTIME_CONFIG_PATH.write_text(
            json.dumps(config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return config


def public_runtime_config() -> dict:
    config = load_runtime_config()
    llm = dict(config.get("llm") or {})
    if "api_key" in llm:
        llm["api_key_set"] = bool(llm.pop("api_key"))
    embedding = dict(config.get("embedding") or {})
    if "api_key" in embedding:
        embedding["api_key_set"] = bool(embedding.pop("api_key"))
    return {"llm": llm, "embedding": embedding, "local_e5": config.get("local_e5") or {}}


def configure_deepseek(api_key: str, model: str = "deepseek-chat") -> dict:
    config = load_runtime_config()
    config["llm"] = {
        "provider": "deepseek",
        "base_url": "https://api.deepseek.com/v1",
        "api_key": api_key,
        "model": model,
        "use_mock": False,
    }
    save_runtime_config(config)
    get_settings.cache_clear()
    return public_runtime_config()


async def configure_local_llm(base_url: str, model: str | None = None) -> dict:
    validation = await validate_local_llm(base_url, model=model)
    normalized_url = validation.get("base_url") or model_base_url_candidates(base_url, "/chat/completions")[0]
    config = load_runtime_config()
    config["llm"] = {
        "provider": "local_llm",
        "base_url": normalized_url,
        "model": validation["model"],
        "use_mock": False,
        "validation": validation,
    }
    save_runtime_config(config)
    get_settings.cache_clear()
    return public_runtime_config()


async def configure_local_embedding(base_url: str, api_key: str = "", model: str | None = None) -> dict:
    validation = await validate_local_embedding(base_url, api_key=api_key, model=model)
    normalized_url = validation.get("base_url") or model_base_url_candidates(base_url, "/embeddings")[0]
    config = load_runtime_config()
    config["embedding"] = {
        "provider": "local_embedding",
        "base_url": normalized_url,
        "api_key": api_key,
        "model": validation["model"],
        "dim": validation["dim"],
        "use_mock": False,
        "validation": validation,
    }
    save_runtime_config(config)
    get_settings.cache_clear()
    return public_runtime_config()


async def validate_local_llm(base_url: str, model: str | None = None) -> dict:
    headers: dict[str, str] = {}
    timeout = httpx.Timeout(20.0, connect=5.0)
    errors: list[str] = []
    async with httpx.AsyncClient(timeout=timeout) as client:
        for candidate_url in model_base_url_candidates(base_url, "/chat/completions"):
            model_name = (
                (model or "").strip()
                or await _discover_first_model(client, candidate_url, headers)
                or "local-llm"
            )
            payload = {
                "model": model_name,
                "messages": [{"role": "user", "content": "回复一句：LLM 连接成功"}],
                "stream": False,
                "temperature": 0.2,
                "max_tokens": 128,
            }
            try:
                response = await client.post(f"{candidate_url}/chat/completions", json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
            except Exception as exc:
                errors.append(f"{candidate_url}/chat/completions -> {exc}")
                continue
            content = str(data.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
            if content:
                return {
                    "status": "ok",
                    "message": "LLM 服务验证通过",
                    "base_url": candidate_url,
                    "model": model_name,
                    "checked_at": datetime.now(UTC).isoformat(),
                    "sample": content[:80],
                }
            errors.append(f"{candidate_url}/chat/completions -> 没有返回 message.content")
    raise ModelValidationError(f"LLM 验证失败：无法调用 /chat/completions：{_format_validation_errors(errors)}")


async def validate_local_embedding(base_url: str, api_key: str = "", model: str | None = None) -> dict:
    headers = _auth_headers(api_key)
    timeout = httpx.Timeout(20.0, connect=5.0)
    errors: list[str] = []
    async with httpx.AsyncClient(timeout=timeout) as client:
        for candidate_url in model_base_url_candidates(base_url, "/embeddings"):
            model_name = (
                (model or "").strip()
                or await _discover_first_model(client, candidate_url, headers)
                or "local-embedding"
            )
            payload = {"model": model_name, "input": "测试 embedding 是否可用"}
            try:
                response = await client.post(f"{candidate_url}/embeddings", json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
            except Exception as exc:
                errors.append(f"{candidate_url}/embeddings -> {exc}")
                continue
            rows = data.get("data") or []
            vector = rows[0].get("embedding") if rows and isinstance(rows[0], dict) else None
            if isinstance(vector, list) and vector and all(
                isinstance(value, Real) and not isinstance(value, bool) for value in vector
            ):
                return {
                    "status": "ok",
                    "message": "Embedding 服务验证通过",
                    "base_url": candidate_url,
                    "model": model_name,
                    "dim": len(vector),
                    "checked_at": datetime.now(UTC).isoformat(),
                }
            errors.append(f"{candidate_url}/embeddings -> 没有返回有效向量")
    raise ModelValidationError(f"Embedding 验证失败：无法调用 /embeddings：{_format_validation_errors(errors)}")


async def _discover_first_model(client: httpx.AsyncClient, base_url: str, headers: dict[str, str]) -> str | None:
    try:
        response = await client.get(f"{base_url}/models", headers=headers)
        response.raise_for_status()
        data = response.json()
    except Exception:
        return None
    models = data.get("data") or []
    if models and isinstance(models[0], dict):
        model_id = models[0].get("id")
        return str(model_id) if model_id else None
    return None


def model_base_url_candidates(raw_url: str, endpoint_suffix: str) -> list[str]:
    value = raw_url.strip()
    if not value:
        raise ModelValidationError("请填写模型服务 URL")
    if "://" not in value:
        value = f"http://{value}"
    parsed = urlparse(value)
    path = parsed.path.rstrip("/")
    endpoint = endpoint_suffix.rstrip("/")

    candidates: list[str] = []
    if path.endswith(endpoint):
        candidates.append(_url_with_path(parsed, path[: -len(endpoint)].rstrip("/")))
        return candidates

    candidates.append(_url_with_path(parsed, path))
    if not path.endswith("/v1"):
        candidates.append(_url_with_path(parsed, f"{path}/v1" if path else "/v1"))
    return list(dict.fromkeys(candidates))


def normalize_openai_base_url(raw_url: str) -> str:
    return model_base_url_candidates(raw_url, "/chat/completions")[0]


def _url_with_path(parsed, path: str) -> str:
    return urlunparse((parsed.scheme, parsed.netloc, path.rstrip("/"), "", "", "")).rstrip("/")


def _format_validation_errors(errors: list[str]) -> str:
    if not errors:
        return "没有可用候选 URL"
    return "；".join(errors[-3:])


def _auth_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"} if api_key.strip() else {}


def configure_local_e5_ready(base_settings: Settings | None = None) -> dict:
    settings = base_settings or get_settings()
    config = load_runtime_config()
    config["embedding"] = {
        "provider": "local_e5",
        "base_url": settings.local_e5_base_url,
        "model": settings.local_e5_model,
        "dim": 384,
        "use_mock": False,
    }
    config["local_e5"] = {"status": "ready", "message": "multilingual-e5-small 已就绪，可以开始测试"}
    save_runtime_config(config)
    get_settings.cache_clear()
    return public_runtime_config()


def settings_with_runtime(settings: Settings | None = None) -> Settings:
    base = settings or get_settings()
    config = load_runtime_config()
    llm = config.get("llm") or {}
    embedding = config.get("embedding") or {}
    updates = {}
    if llm.get("provider") == "deepseek" and llm.get("api_key"):
        updates.update(
            {
                "llm_provider": "deepseek",
                "llm_base_url": llm.get("base_url") or "https://api.deepseek.com/v1",
                "llm_api_key": llm["api_key"],
                "llm_model": llm.get("model") or "deepseek-chat",
                "use_mock_llm": False,
            }
        )
    elif llm.get("provider") == "local_llm" and llm.get("base_url"):
        updates.update(
            {
                "llm_provider": "local_llm",
                "llm_base_url": llm.get("base_url"),
                "llm_api_key": "",
                "llm_model": llm.get("model") or "local-llm",
                "use_mock_llm": False,
            }
        )
    if embedding.get("provider") in {"local_e5", "local_embedding"}:
        updates.update(
            {
                "embed_provider": embedding.get("provider"),
                "embed_base_url": embedding.get("base_url") or base.local_e5_base_url,
                "embed_api_key": embedding.get("api_key") or "",
                "embed_model": embedding.get("model") or base.local_e5_model,
                "embed_dim": int(embedding.get("dim") or 384),
                "use_mock_embedding": False,
            }
        )
    return base.model_copy(update=updates)
