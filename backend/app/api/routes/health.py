from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.common import ok
from app.services.model_gateway.runtime_config import settings_with_runtime

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def health():
    return ok({"status": "ok"})


@router.get("/models")
def models_health():
    settings = settings_with_runtime(get_settings())
    llm_mock = settings.use_mock_llm or not settings.llm_base_url
    embed_mock = settings.use_mock_embedding or not settings.embed_base_url
    return ok(
        {
            "llm": {
                "provider": "mock" if llm_mock else settings.llm_provider,
                "model": settings.llm_model,
                "base_url_configured": bool(settings.llm_base_url),
            },
            "embedding": {
                "provider": "mock" if embed_mock else settings.embed_provider,
                "model": settings.embed_model,
                "dimension": settings.embed_dim,
                "base_url_configured": bool(settings.embed_base_url),
            },
        }
    )


@router.get("/dependencies")
def dependencies_health(db: Session = Depends(get_db)):
    dependencies = {}
    try:
        db.execute(text("select 1"))
        dependencies["database"] = {"status": "ok"}
    except Exception as exc:
        dependencies["database"] = {"status": "failed", "message": str(exc)}
    settings = get_settings()
    dependencies["redis"] = {"status": "configured", "url": settings.redis_url}
    dependencies["minio"] = {"status": "configured", "endpoint": settings.minio_endpoint}
    dependencies["qdrant"] = {"status": "configured", "url": settings.qdrant_url}
    dependencies["opensearch"] = {
        "status": "disabled" if not settings.enable_opensearch else "configured",
        "url": settings.opensearch_url,
    }
    return ok(dependencies)
