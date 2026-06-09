from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import admin, auth, chat, document, health, knowledge_base
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.base import Base
from app.db.schema import ensure_local_schema
from app.db.seed import seed_defaults
from app.db.session import SessionLocal, engine

settings = get_settings()
configure_logging()

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix=settings.api_prefix)
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(knowledge_base.router, prefix=settings.api_prefix)
app.include_router(document.router, prefix=settings.api_prefix)
app.include_router(chat.router, prefix=settings.api_prefix)
app.include_router(admin.router, prefix=settings.api_prefix)


@app.on_event("startup")
def startup() -> None:
    if settings.auto_create_tables:
        Base.metadata.create_all(bind=engine)
        ensure_local_schema(engine)
        with SessionLocal() as db:
            seed_defaults(db)


@app.get("/")
def root():
    return {"name": settings.app_name, "api": settings.api_prefix}
