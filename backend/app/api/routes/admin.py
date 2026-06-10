from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, inspect, text
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_user, serialize_user
from app.core.config import get_settings
from app.core.security import get_password_hash
from app.db.models import AuditLog, Document, ModelCallLog, User
from app.db.session import engine, get_db
from app.schemas.admin import (
    DeepSeekConfigRequest,
    LocalEmbeddingConfigRequest,
    LocalLLMConfigRequest,
    RetrievalTestRequest,
    UserCreate,
)
from app.schemas.common import ok
from app.services.indexing.vector_indexer import vector_indexer
from app.services.model_gateway.local_e5_manager import local_e5_manager
from app.services.model_gateway.runtime_config import (
    ModelValidationError,
    configure_deepseek,
    configure_local_embedding,
    configure_local_llm,
    public_runtime_config,
    settings_with_runtime,
)
from app.services.permissions.permission_service import can_admin, can_manage_shared_kb
from app.services.rag.retriever import retrieve_evidence_with_trace

router = APIRouter(prefix="/admin", tags=["admin"])


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not can_admin(current_user):
        raise HTTPException(status_code=403, detail="无权访问管理后台")
    return current_user


@router.get("/users")
def users(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    return ok([serialize_user(user) for user in db.query(User).order_by(User.created_at).all()])


@router.post("/users")
def create_user(payload: UserCreate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    if not can_manage_shared_kb(current_user):
        raise HTTPException(status_code=403, detail="只有系统管理员可以创建账号")
    exists = db.query(User).filter(User.username == payload.username).one_or_none()
    if exists:
        raise HTTPException(status_code=400, detail="账号已存在")
    role = payload.role if payload.role in {"system_admin", "auditor", "audit_manager"} else "auditor"
    user = User(
        username=payload.username,
        password_hash=get_password_hash(payload.password),
        display_name=payload.display_name,
        role=role,
        department=payload.department,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return ok(serialize_user(user))


@router.get("/database/overview")
def database_overview(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    if not can_manage_shared_kb(current_user):
        raise HTTPException(status_code=403, detail="只有系统管理员可以管理数据库")
    inspector = inspect(engine)
    preparer = engine.dialect.identifier_preparer
    tables = []
    for table_name in inspector.get_table_names():
        quoted_table = preparer.quote(table_name)
        count = db.execute(text(f"select count(*) from {quoted_table}")).scalar_one()
        tables.append({"table": table_name, "rows": count})
    db_stats = {
        "users": db.query(func.count(User.id)).scalar(),
        "documents": db.query(func.count(Document.id)).scalar(),
        "audit_logs": db.query(func.count(AuditLog.id)).scalar(),
        "model_call_logs": db.query(func.count(ModelCallLog.id)).scalar(),
    }
    return ok({"dialect": engine.dialect.name, "tables": tables, "stats": db_stats})


@router.post("/retrieval/test")
async def test_retrieval(
    payload: RetrievalTestRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="请输入测试问题")
    result = await retrieve_evidence_with_trace(
        db,
        payload.query.strip(),
        kb_id=payload.kb_id,
        top_k=max(1, min(payload.top_k, 20)),
        current_user=current_user,
    )
    result["vector_index"] = vector_indexer.status()
    return ok(result)


@router.post("/database/vacuum")
def vacuum_database(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    if not can_manage_shared_kb(current_user):
        raise HTTPException(status_code=403, detail="只有系统管理员可以管理数据库")
    if engine.dialect.name == "sqlite":
        db.commit()
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text("vacuum"))
        return ok({"status": "done", "message": "SQLite 数据库整理完成"})
    return ok({"status": "skipped", "message": "当前数据库类型不需要手动 VACUUM"})


@router.get("/model-setup")
def model_setup(current_user: User = Depends(require_admin)):
    if not can_manage_shared_kb(current_user):
        raise HTTPException(status_code=403, detail="只有系统管理员可以配置测试模型")
    config = public_runtime_config()
    config["local_e5"] = local_e5_manager.status()
    return ok(config)


@router.post("/model-setup/deepseek")
async def setup_deepseek(payload: DeepSeekConfigRequest, current_user: User = Depends(require_admin)):
    if not can_manage_shared_kb(current_user):
        raise HTTPException(status_code=403, detail="只有系统管理员可以配置测试模型")
    if not payload.api_key.strip():
        raise HTTPException(status_code=400, detail="请填写 DeepSeek API Key")
    try:
        return ok(await configure_deepseek(payload.api_key.strip(), payload.model.strip() or "deepseek-chat"))
    except ModelValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/model-setup/llm")
async def setup_local_llm(payload: LocalLLMConfigRequest, current_user: User = Depends(require_admin)):
    if not can_manage_shared_kb(current_user):
        raise HTTPException(status_code=403, detail="只有系统管理员可以配置测试模型")
    try:
        return ok(await configure_local_llm(payload.base_url, model=payload.model))
    except ModelValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/model-setup/embedding")
async def setup_local_embedding(payload: LocalEmbeddingConfigRequest, current_user: User = Depends(require_admin)):
    if not can_manage_shared_kb(current_user):
        raise HTTPException(status_code=403, detail="只有系统管理员可以配置测试模型")
    try:
        return ok(await configure_local_embedding(payload.base_url, api_key=payload.api_key, model=payload.model))
    except ModelValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/model-setup/local-e5/start")
def start_local_e5(current_user: User = Depends(require_admin)):
    if not can_manage_shared_kb(current_user):
        raise HTTPException(status_code=403, detail="只有系统管理员可以配置测试模型")
    return ok(local_e5_manager.start())


@router.get("/model-setup/local-e5/status")
def local_e5_status(current_user: User = Depends(require_admin)):
    if not can_manage_shared_kb(current_user):
        raise HTTPException(status_code=403, detail="只有系统管理员可以配置测试模型")
    return ok(local_e5_manager.status())


@router.get("/audit-logs")
def audit_logs(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    logs = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(200).all()
    return ok(
        [
            {
                "id": log.id,
                "user_id": log.user_id,
                "action": log.action,
                "target_type": log.target_type,
                "target_id": log.target_id,
                "detail": log.detail_json,
                "status": log.status,
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ]
    )


@router.get("/tasks")
def tasks(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    documents = db.query(Document).order_by(Document.updated_at.desc()).limit(200).all()
    return ok(
        [
            {
                "document_id": doc.id,
                "file_name": doc.file_name,
                "status": doc.status,
                "error_message": doc.error_message,
                "updated_at": doc.updated_at.isoformat(),
            }
            for doc in documents
        ]
    )


@router.get("/model-call-logs")
def model_call_logs(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    logs = db.query(ModelCallLog).order_by(ModelCallLog.created_at.desc()).limit(200).all()
    settings = settings_with_runtime(get_settings())
    return ok(
        {
            "status": {
                "llm": {"configured": bool(settings.llm_base_url), "mock": settings.use_mock_llm},
                "embedding": {
                    "configured": bool(settings.embed_base_url),
                    "mock": settings.use_mock_embedding,
                },
                "qdrant": vector_indexer.status(),
                "minio": {"endpoint": settings.minio_endpoint},
                "postgresql": {"url": settings.database_url.split("@")[-1]},
                "redis": {"url": settings.redis_url},
            },
            "logs": [
                {
                    "id": log.id,
                    "provider": log.provider,
                    "model_name": log.model_name,
                    "endpoint_type": log.endpoint_type,
                    "response_time_ms": log.response_time_ms,
                    "status": log.status,
                    "error_message": log.error_message,
                    "created_at": log.created_at.isoformat(),
                }
                for log in logs
            ],
        }
    )
