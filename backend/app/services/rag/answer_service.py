from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import User
from app.services.chat_context.context_manager import ChatContextManager
from app.services.model_gateway.gateway import get_llm_client
from app.services.rag.citation_builder import build_citations
from app.services.rag.retriever import retrieve_evidence


async def answer_question(
    db: Session,
    question: str,
    kb_id: str | None = None,
    kb_ids: list[str] | None = None,
    mode: str = "normal",
    uploaded_files: list[dict] | None = None,
    conversation_id: str | None = None,
    current_message_id: str | None = None,
    settings: Settings | None = None,
    current_user: User | None = None,
) -> dict:
    evidence = await retrieve_evidence(db, question, kb_id=kb_id, kb_ids=kb_ids, current_user=current_user)
    messages = ChatContextManager(settings).build_messages(
        db,
        conversation_id=conversation_id,
        question=question,
        mode=mode,
        evidence=evidence,
        uploaded_files=uploaded_files,
        current_message_id=current_message_id,
    )
    llm_response = await get_llm_client().chat(messages)
    return {"answer": llm_response["answer"], "citations": build_citations(evidence), "evidence": evidence}
