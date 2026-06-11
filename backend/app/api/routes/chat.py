from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_user
from app.core.config import get_settings
from app.db.models import Conversation, Message, TempFile, User
from app.db.session import get_db
from app.schemas.chat import (
    ChatMessageCreate,
    ChatMessageUpdate,
    ChatRegenerateRequest,
    ConversationCreate,
    ConversationUpdate,
    FeedbackCreate,
)
from app.schemas.common import ok
from app.services.audit.audit_logger import log_action, text_digest
from app.services.chat_context.context_manager import ChatContextManager
from app.services.model_gateway.gateway import get_llm_client
from app.services.parser.document_parser import SUPPORTED_EXTENSIONS
from app.services.parser.excel_analyzer import analyze_excel_question
from app.services.parser.progress import progress_for_status
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
    client_request_id = _clean_client_request_id(payload.client_request_id)
    if client_request_id:
        existing = _conversation_by_client_request(db, current_user.id, client_request_id)
        if existing:
            return ok(_conversation_dict(existing))
    metadata = _conversation_scope_metadata(payload.kb_ids, payload.document_ids, payload.scope_label)
    metadata["auto_title"] = True
    if client_request_id:
        metadata["client_request_id"] = client_request_id
    conversation = Conversation(
        user_id=current_user.id,
        title=payload.title or "新会话",
        mode="normal",
        metadata_json=metadata,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return ok(_conversation_dict(conversation))


@router.get("/conversations")
def list_conversations(
    q: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Conversation).filter(Conversation.user_id == current_user.id)
    search = " ".join((q or "").split()).strip()
    if search:
        filters = []
        for term in _search_terms(search):
            pattern = f"%{term}%"
            filters.extend(
                [
                    Conversation.title.ilike(pattern),
                    Conversation.messages.any(Message.content.ilike(pattern)),
                ]
            )
        query = query.filter(or_(*filters))
    conversations = query.order_by(Conversation.updated_at.desc()).limit(100).all()
    return ok([_conversation_dict(item, search=search) for item in conversations])


@router.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation = db.get(Conversation, conversation_id)
    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    return ok(_conversation_dict(conversation, include_messages=True))


@router.patch("/conversations/{conversation_id}")
def update_conversation(
    conversation_id: str,
    payload: ConversationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation = db.get(Conversation, conversation_id)
    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    title = _clean_title(payload.title)
    if not title:
        raise HTTPException(status_code=400, detail="标题不能为空")
    conversation.title = title
    metadata = dict(conversation.metadata_json or {})
    metadata["auto_title"] = False
    conversation.metadata_json = metadata
    db.commit()
    db.refresh(conversation)
    return ok(_conversation_dict(conversation))


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation = db.get(Conversation, conversation_id)
    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    storage = ObjectStorage()
    for temp_file in list(conversation.temp_files):
        if temp_file.minio_object_key:
            storage.remove(temp_file.minio_object_key)
    db.delete(conversation)
    db.commit()
    return ok({"deleted": conversation_id})


@router.post("/conversations/{conversation_id}/messages")
async def create_message(
    conversation_id: str,
    payload: ChatMessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation = db.get(Conversation, conversation_id)
    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="会话不存在")

    pending_files = _pending_temp_files(db, conversation_id)
    processing_files = [item for item in pending_files if item.status in {"uploaded", "parsing"}]
    if processing_files:
        raise HTTPException(status_code=400, detail="上传文件仍在解析，请等待解析完成后再提问")
    ready_files = [item for item in pending_files if item.status == "ready"]

    previous_user_messages = db.query(Message).filter(
        Message.conversation_id == conversation_id,
        Message.role == "user",
    ).count()
    should_generate_title = previous_user_messages == 0 and _should_auto_title(conversation)
    if previous_user_messages == 0 and _is_default_conversation_title(conversation.title):
        conversation.title = _title_from_question(payload.content)

    user_message = Message(conversation_id=conversation_id, role="user", content=payload.content)
    db.add(user_message)
    db.flush()
    for temp_file in pending_files:
        metadata = dict(temp_file.metadata_json or {})
        metadata["used_message_id"] = user_message.id
        temp_file.metadata_json = metadata
    db.commit()
    log_action(db, "用户提问", current_user.id, "conversation", conversation_id, text_digest(payload.content))

    assistant_message = await _generate_assistant_for_user_message(
        db,
        conversation,
        user_message,
        current_user,
        kb_id=payload.kb_id,
        kb_ids=payload.kb_ids,
        document_ids=payload.document_ids,
        mode=payload.mode,
        uploaded_files=ready_files,
    )
    if should_generate_title:
        await _apply_generated_title(db, conversation, user_message, assistant_message)
        db.refresh(assistant_message)
    return ok(
        {
            "user_message": _message_dict(user_message, attachments=[_temp_file_dict(item) for item in pending_files]),
            "message": _message_dict(assistant_message),
            "conversation": _conversation_dict(conversation),
        }
    )


@router.patch("/conversations/{conversation_id}/messages/{message_id}")
async def edit_user_message_and_regenerate(
    conversation_id: str,
    message_id: str,
    payload: ChatMessageUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation = _owned_conversation(db, conversation_id, current_user)
    user_message = db.get(Message, message_id)
    if not user_message or user_message.conversation_id != conversation_id or user_message.role != "user":
        raise HTTPException(status_code=404, detail="用户消息不存在")
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="问题不能为空")

    messages = _ordered_messages(db, conversation_id)
    target_index = _message_index(messages, message_id)
    if target_index is None:
        raise HTTPException(status_code=404, detail="用户消息不存在")
    user_message.content = content
    should_generate_title = target_index == 0 and _should_auto_title(conversation)
    if target_index == 0 and _is_default_conversation_title(conversation.title):
        conversation.title = _title_from_question(content)
    _delete_messages_and_attached_temp_files(db, conversation, messages[target_index + 1 :])
    _clear_conversation_memory(db, conversation)
    db.commit()

    assistant_message = await _generate_assistant_for_user_message(
        db,
        conversation,
        user_message,
        current_user,
        kb_id=payload.kb_id,
        kb_ids=payload.kb_ids,
        document_ids=payload.document_ids,
        mode=payload.mode,
        uploaded_files=_temp_files_for_message(db, conversation_id, user_message.id),
    )
    if should_generate_title:
        await _apply_generated_title(db, conversation, user_message, assistant_message)
    log_action(db, "编辑问题并重新生成", current_user.id, "message", user_message.id, text_digest(content))
    db.refresh(conversation)
    return ok(_conversation_dict(conversation, include_messages=True))


@router.post("/conversations/{conversation_id}/messages/{message_id}/regenerate")
async def regenerate_assistant_message(
    conversation_id: str,
    message_id: str,
    payload: ChatRegenerateRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation = _owned_conversation(db, conversation_id, current_user)
    assistant_message = db.get(Message, message_id)
    if (
        not assistant_message
        or assistant_message.conversation_id != conversation_id
        or assistant_message.role != "assistant"
    ):
        raise HTTPException(status_code=404, detail="助手消息不存在")

    messages = _ordered_messages(db, conversation_id)
    assistant_index = _message_index(messages, message_id)
    if assistant_index is None:
        raise HTTPException(status_code=404, detail="助手消息不存在")
    user_message = next((message for message in reversed(messages[:assistant_index]) if message.role == "user"), None)
    if not user_message:
        raise HTTPException(status_code=400, detail="找不到可重新生成的用户问题")

    _delete_messages_and_attached_temp_files(db, conversation, messages[assistant_index:])
    _clear_conversation_memory(db, conversation)
    db.commit()
    assistant_message = await _generate_assistant_for_user_message(
        db,
        conversation,
        user_message,
        current_user,
        kb_id=payload.kb_id if payload else None,
        kb_ids=payload.kb_ids if payload else None,
        document_ids=payload.document_ids if payload else None,
        mode=payload.mode if payload else "normal",
        uploaded_files=_temp_files_for_message(db, conversation_id, user_message.id),
    )
    log_action(db, "重新生成回答", current_user.id, "message", assistant_message.id, {"source_message_id": message_id})
    db.refresh(conversation)
    return ok(_conversation_dict(conversation, include_messages=True))


@router.post("/conversations/{conversation_id}/temp-files")
async def upload_temp_file(
    conversation_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    settings = get_settings()
    conversation = db.get(Conversation, conversation_id)
    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    if len(_pending_temp_files(db, conversation_id)) >= 5:
        raise HTTPException(status_code=400, detail="单次最多上传 5 个文件")
    ext = Path(file.filename or "").suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="当前格式不支持，请上传Word/Excel/PDF/图片文件")
    object_key, local_path = await ObjectStorage(settings).save_upload(file, prefix="temp-files")
    if local_path.stat().st_size > settings.max_upload_bytes:
        local_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"单文件大小不能超过{settings.max_upload_mb}MB")

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
    conversation = db.get(Conversation, conversation_id)
    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    if not temp_file or temp_file.conversation_id != conversation_id:
        raise HTTPException(status_code=404, detail="临时文件不存在")
    if (temp_file.metadata_json or {}).get("used_message_id"):
        raise HTTPException(status_code=400, detail="已发送的附件不能从历史消息中删除")
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


def _owned_conversation(db: Session, conversation_id: str, current_user: User) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    return conversation


def _ordered_messages(db: Session, conversation_id: str) -> list[Message]:
    return (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
        .all()
    )


def _message_index(messages: list[Message], message_id: str) -> int | None:
    for index, message in enumerate(messages):
        if message.id == message_id:
            return index
    return None


def _delete_messages_and_attached_temp_files(
    db: Session,
    conversation: Conversation,
    messages: list[Message],
) -> None:
    deleted_message_ids = {message.id for message in messages}
    if not deleted_message_ids:
        return
    storage = ObjectStorage()
    for temp_file in list(conversation.temp_files):
        if (temp_file.metadata_json or {}).get("used_message_id") in deleted_message_ids:
            if temp_file.minio_object_key:
                storage.remove(temp_file.minio_object_key)
            db.delete(temp_file)
    for message in messages:
        db.delete(message)


def _clear_conversation_memory(db: Session, conversation: Conversation) -> None:
    if conversation.memory:
        db.delete(conversation.memory)


async def _generate_assistant_for_user_message(
    db: Session,
    conversation: Conversation,
    user_message: Message,
    current_user: User,
    kb_id: str | None = None,
    kb_ids: list[str] | None = None,
    document_ids: list[str] | None = None,
    mode: str = "normal",
    uploaded_files: list[TempFile] | None = None,
) -> Message:
    attached_files = uploaded_files or []
    scope = _conversation_scope(conversation)
    effective_kb_ids = kb_ids or scope.get("kb_ids", [])
    effective_document_ids = document_ids or scope.get("document_ids", [])
    effective_document_ids = effective_document_ids or None
    effective_kb_id = kb_id or (effective_kb_ids[0] if effective_kb_ids else None)

    deterministic_answer = _try_temp_excel_analysis(attached_files, user_message.content)
    if deterministic_answer:
        answer = deterministic_answer + "\n\n以上为 pandas 确定性计算结果，建议结合原始 Excel 核对。"
        citations = []
    else:
        result = await answer_question(
            db,
            user_message.content,
            kb_id=effective_kb_id,
            kb_ids=effective_kb_ids,
            document_ids=effective_document_ids,
            mode="normal",
            uploaded_files=_temp_file_context(attached_files),
            conversation_id=conversation.id,
            current_message_id=user_message.id,
            current_user=current_user,
        )
        answer = result["answer"]
        citations = result["citations"]

    assistant_message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=answer,
        citations_json=citations,
    )
    db.add(assistant_message)
    db.commit()
    ChatContextManager().update_memory(db, conversation.id)
    db.refresh(assistant_message)
    return assistant_message


async def _apply_generated_title(
    db: Session,
    conversation: Conversation,
    user_message: Message,
    assistant_message: Message,
) -> None:
    fallback = _title_from_question(user_message.content)
    conversation.title = await _generate_conversation_title(user_message.content, assistant_message.content, fallback)
    metadata = dict(conversation.metadata_json or {})
    metadata["auto_title"] = True
    conversation.metadata_json = metadata
    db.add(conversation)
    db.commit()
    db.refresh(conversation)


async def _generate_conversation_title(user_text: str, assistant_text: str, fallback: str) -> str:
    try:
        response = await get_llm_client().chat(
            [
                {
                    "role": "system",
                    "content": (
                        "你是审计 AI 助手的会话标题生成器。"
                        "根据第一轮用户问题和助手回答生成一个简洁中文标题。"
                        "只输出标题，不要解释，不要引号，不要标点结尾。"
                        "标题应为 6 到 18 个汉字，能概括会话主旨。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"用户问题：{user_text[:800]}\n\n"
                        f"助手回答：{assistant_text[:1200]}\n\n"
                        "请输出会话标题："
                    ),
                },
            ]
        )
        return _clean_generated_title(response.get("answer", ""), fallback)
    except Exception:
        return fallback


def _clean_generated_title(raw: str, fallback: str) -> str:
    title = " ".join((raw or "").strip().split())
    for prefix in ("标题：", "标题:", "会话标题：", "会话标题:"):
        if title.startswith(prefix):
            title = title[len(prefix) :].strip()
    title = title.strip("「」『』“”\"'`。.!！?？：:")
    if not title:
        return fallback
    return title[:24]


def _should_auto_title(conversation: Conversation) -> bool:
    metadata = conversation.metadata_json or {}
    if isinstance(metadata, dict) and metadata.get("auto_title") is False:
        return False
    return True


def _pending_temp_files(db: Session, conversation_id: str) -> list[TempFile]:
    files = db.query(TempFile).filter(TempFile.conversation_id == conversation_id).order_by(TempFile.created_at).all()
    return [item for item in files if not (item.metadata_json or {}).get("used_message_id")]


def _temp_files_for_message(db: Session, conversation_id: str, message_id: str) -> list[TempFile]:
    files = (
        db.query(TempFile)
        .filter(TempFile.conversation_id == conversation_id)
        .order_by(TempFile.created_at)
        .all()
    )
    return [item for item in files if (item.metadata_json or {}).get("used_message_id") == message_id]


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


def _conversation_dict(conversation: Conversation, include_messages: bool = False, search: str = "") -> dict:
    scope = _conversation_scope(conversation)
    data = {
        "id": conversation.id,
        "title": conversation.title,
        "mode": conversation.mode,
        "scope": scope,
        "created_at": conversation.created_at.isoformat(),
        "updated_at": conversation.updated_at.isoformat(),
    }
    if search:
        data["search_match"] = _conversation_search_match(conversation, search)
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


def _conversation_search_match(conversation: Conversation, search: str) -> dict:
    search = " ".join(search.split()).strip()
    if not search:
        return {}
    terms = _search_terms(search)
    title_match = _best_search_match(conversation.title, terms)
    if title_match:
        return {
            "source": "title",
            "title": conversation.title,
            "snippet": conversation.title,
            "matched_text": title_match[1],
        }
    for message in sorted(conversation.messages, key=lambda item: item.created_at):
        message_match = _best_search_match(message.content, terms)
        if message_match:
            index, matched_text = message_match
            return {
                "source": "message",
                "title": conversation.title,
                "snippet": _snippet_around(message.content, index, len(matched_text)),
                "role": message.role,
                "matched_text": matched_text,
            }
    return {"source": "none", "title": conversation.title, "snippet": ""}


def _search_terms(search: str) -> list[str]:
    normalized = " ".join(search.split()).strip()
    if not normalized:
        return []
    terms = [normalized, *normalized.split()]
    return list(dict.fromkeys(term for term in terms if term))


def _best_search_match(text: str, terms: list[str]) -> tuple[int, str] | None:
    folded_text = text.casefold()
    best: tuple[int, str] | None = None
    for term in terms:
        index = folded_text.find(term.casefold())
        if index < 0:
            continue
        if best is None or index < best[0] or (index == best[0] and len(term) > len(best[1])):
            best = (index, text[index : index + len(term)])
    return best


def _snippet_around(text: str, start: int, length: int, context: int = 32) -> str:
    left = max(0, start - context)
    right = min(len(text), start + length + context)
    snippet = " ".join(text[left:right].split())
    if left > 0:
        snippet = f"…{snippet}"
    if right < len(text):
        snippet = f"{snippet}…"
    return snippet


def _conversation_scope_metadata(kb_ids: list[str] | None, document_ids: list[str] | None, label: str | None) -> dict:
    clean_kb_ids = _unique_strings(kb_ids or [])
    clean_document_ids = _unique_strings(document_ids or [])
    clean_label = _clean_title(label or "")
    if not clean_kb_ids and not clean_document_ids:
        return {}
    scope_type = "documents" if clean_document_ids else "knowledge_bases"
    return {
        "scope": {
            "type": scope_type,
            "label": clean_label,
            "kb_ids": clean_kb_ids,
            "document_ids": clean_document_ids,
        }
    }


def _clean_client_request_id(value: str | None) -> str:
    return " ".join((value or "").split()).strip()[:160]


def _conversation_by_client_request(db: Session, user_id: str, client_request_id: str) -> Conversation | None:
    if not client_request_id:
        return None
    recent = (
        db.query(Conversation)
        .filter(Conversation.user_id == user_id)
        .order_by(Conversation.created_at.desc())
        .limit(200)
        .all()
    )
    return next(
        (
            conversation
            for conversation in recent
            if (conversation.metadata_json or {}).get("client_request_id") == client_request_id
        ),
        None,
    )


def _conversation_scope(conversation: Conversation) -> dict:
    metadata = conversation.metadata_json or {}
    scope = metadata.get("scope") if isinstance(metadata, dict) else None
    if not isinstance(scope, dict):
        return {}
    return {
        "type": str(scope.get("type") or ""),
        "label": str(scope.get("label") or ""),
        "kb_ids": _unique_strings(scope.get("kb_ids") or []),
        "document_ids": _unique_strings(scope.get("document_ids") or []),
    }


def _unique_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def _clean_title(value: str) -> str:
    return " ".join(value.split()).strip()[:80]


def _is_default_conversation_title(title: str) -> bool:
    return title.strip() in {"", "新会话", "审计问答"}


def _title_from_question(question: str) -> str:
    clean = _clean_title(question)
    return clean[:24] or "新会话"


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
    metadata = temp_file.metadata_json or {}
    parser_detail = metadata.get("parser_detail") or ""
    capabilities = metadata.get("capabilities")
    if isinstance(capabilities, list) and capabilities and not parser_detail:
        parser_detail = "能力：" + "、".join(str(item) for item in capabilities)
    progress = progress_for_status(temp_file.status, metadata)
    return {
        "id": temp_file.id,
        "file_name": temp_file.file_name,
        "status": temp_file.status,
        "error_message": metadata.get("error_message", ""),
        "status_message": metadata.get("status_message", ""),
        "parser_provider": metadata.get("parser_provider") or metadata.get("provider", ""),
        "parser_detail": parser_detail,
        **progress,
        "expires_at": temp_file.expires_at.isoformat() if temp_file.expires_at else None,
    }
