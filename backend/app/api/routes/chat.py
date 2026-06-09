from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_user
from app.core.config import get_settings
from app.db.models import Conversation, Message, TempFile, User
from app.db.session import get_db
from app.schemas.chat import ChatMessageCreate, ConversationCreate, FeedbackCreate
from app.schemas.common import ok
from app.services.audit.audit_logger import log_action, text_digest
from app.services.chat_context.context_manager import ChatContextManager
from app.services.parser.document_parser import SUPPORTED_EXTENSIONS
from app.services.parser.excel_analyzer import analyze_excel_question
from app.services.rag.answer_service import answer_question
from app.services.storage.minio_client import ObjectStorage
from app.services.tasks.temp_file_tasks import process_temp_file_in_background

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/conversations")
def create_conversation(
    payload: ConversationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation = Conversation(user_id=current_user.id, title=payload.title or "新会话", mode="normal")
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return ok(_conversation_dict(conversation))


@router.get("/conversations")
def list_conversations(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    conversations = (
        db.query(Conversation)
        .filter(Conversation.user_id == current_user.id)
        .order_by(Conversation.updated_at.desc())
        .limit(100)
        .all()
    )
    return ok([_conversation_dict(item) for item in conversations])


@router.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation = db.get(Conversation, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="会话不存在")
    return ok(_conversation_dict(conversation, include_messages=True))


@router.post("/conversations/{conversation_id}/messages")
async def create_message(
    conversation_id: str,
    payload: ChatMessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation = db.get(Conversation, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="会话不存在")

    pending_files = _pending_temp_files(db, conversation_id)
    processing_files = [item for item in pending_files if item.status in {"uploaded", "parsing"}]
    if processing_files:
        raise HTTPException(status_code=400, detail="上传文件仍在解析，请等待解析完成后再提问")
    ready_files = [item for item in pending_files if item.status == "ready"]

    user_message = Message(conversation_id=conversation_id, role="user", content=payload.content)
    db.add(user_message)
    db.flush()
    for temp_file in pending_files:
        metadata = dict(temp_file.metadata_json or {})
        metadata["used_message_id"] = user_message.id
        temp_file.metadata_json = metadata
    db.commit()
    log_action(db, "用户提问", current_user.id, "conversation", conversation_id, text_digest(payload.content))

    deterministic_answer = _try_temp_excel_analysis(ready_files, payload.content)
    if deterministic_answer:
        answer = deterministic_answer + "\n\n以上为 pandas 确定性计算结果，建议结合原始 Excel 核对。"
        citations = []
    else:
        result = await answer_question(
            db,
            payload.content,
            kb_id=payload.kb_id,
            kb_ids=payload.kb_ids,
            mode="normal",
            uploaded_files=_temp_file_context(ready_files),
            conversation_id=conversation_id,
            current_message_id=user_message.id,
            current_user=current_user,
        )
        answer = result["answer"]
        citations = result["citations"]

    assistant_message = Message(
        conversation_id=conversation_id,
        role="assistant",
        content=answer,
        citations_json=citations,
    )
    db.add(assistant_message)
    db.commit()
    ChatContextManager().update_memory(db, conversation_id)
    return ok(
        {
            "user_message": _message_dict(user_message, attachments=[_temp_file_dict(item) for item in pending_files]),
            "message": _message_dict(assistant_message),
        }
    )


@router.post("/conversations/{conversation_id}/temp-files")
async def upload_temp_file(
    conversation_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    settings = get_settings()
    if len(_pending_temp_files(db, conversation_id)) >= 5:
        raise HTTPException(status_code=400, detail="单次最多上传 5 个文件")
    ext = Path(file.filename or "").suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="当前格式不支持，请上传Word/Excel/PDF/图片文件")
    object_key, local_path = await ObjectStorage(settings).save_upload(file, prefix="temp-files")
    if local_path.stat().st_size > settings.max_upload_bytes:
        local_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="单文件大小不能超过50MB")

    temp_file = TempFile(
        conversation_id=conversation_id,
        file_name=file.filename or local_path.name,
        minio_object_key=object_key,
        status="parsing",
        parsed_text="",
        metadata_json={
            "local_path": str(local_path),
        },
        expires_at=datetime.now(UTC) + timedelta(hours=settings.temp_file_ttl_hours),
    )
    db.add(temp_file)
    db.commit()
    log_action(db, "上传文件提问", current_user.id, "temp_file", temp_file.id, {"file_name": temp_file.file_name})
    background_tasks.add_task(process_temp_file_in_background, temp_file.id)
    return ok(_temp_file_dict(temp_file))


@router.delete("/conversations/{conversation_id}/temp-files/{file_id}")
def delete_temp_file(
    conversation_id: str,
    file_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    temp_file = db.get(TempFile, file_id)
    if not temp_file or temp_file.conversation_id != conversation_id:
        raise HTTPException(status_code=404, detail="临时文件不存在")
    ObjectStorage().remove(temp_file.minio_object_key)
    db.delete(temp_file)
    db.commit()
    return ok({"deleted": file_id})


@router.post("/feedback")
def feedback(
    payload: FeedbackCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    log_action(
        db,
        "点赞 / 点踩",
        current_user.id,
        "message",
        payload.message_id,
        {"feedback_type": payload.feedback_type, "detail": payload.detail},
    )
    return ok({"received": True})


def _pending_temp_files(db: Session, conversation_id: str) -> list[TempFile]:
    files = db.query(TempFile).filter(TempFile.conversation_id == conversation_id).order_by(TempFile.created_at).all()
    return [item for item in files if not (item.metadata_json or {}).get("used_message_id")]


def _temp_file_context(files: list[TempFile]) -> list[dict]:
    return [
        {
            "id": item.id,
            "file_name": item.file_name,
            "text": item.parsed_text,
            "metadata": item.metadata_json,
        }
        for item in files
        if item.parsed_text.strip()
    ]


def _try_temp_excel_analysis(files: list[TempFile], question: str) -> str | None:
    outputs = []
    for temp_file in files:
        path_raw = (temp_file.metadata_json or {}).get("local_path")
        if path_raw and Path(path_raw).suffix.lower() in {".xls", ".xlsx"}:
            result = analyze_excel_question(Path(path_raw), question)
            if result:
                outputs.append(f"文件：{temp_file.file_name}\n{result}")
    return "\n\n".join(outputs) if outputs else None


def _conversation_dict(conversation: Conversation, include_messages: bool = False) -> dict:
    data = {
        "id": conversation.id,
        "title": conversation.title,
        "mode": conversation.mode,
        "created_at": conversation.created_at.isoformat(),
        "updated_at": conversation.updated_at.isoformat(),
    }
    if include_messages:
        attachments_by_message: dict[str, list[dict]] = {}
        pending_temp_files = []
        for item in conversation.temp_files:
            used_message_id = (item.metadata_json or {}).get("used_message_id")
            if used_message_id:
                attachments_by_message.setdefault(used_message_id, []).append(_temp_file_dict(item))
            else:
                pending_temp_files.append(_temp_file_dict(item))
        data["messages"] = [
            _message_dict(message, attachments=attachments_by_message.get(message.id, []))
            for message in conversation.messages
        ]
        data["temp_files"] = pending_temp_files
    return data


def _message_dict(message: Message, attachments: list[dict] | None = None) -> dict:
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "citations": message.citations_json,
        "attachments": attachments or [],
        "created_at": message.created_at.isoformat(),
    }


def _temp_file_dict(temp_file: TempFile) -> dict:
    return {
        "id": temp_file.id,
        "file_name": temp_file.file_name,
        "status": temp_file.status,
        "error_message": (temp_file.metadata_json or {}).get("error_message", ""),
        "expires_at": temp_file.expires_at.isoformat() if temp_file.expires_at else None,
    }
