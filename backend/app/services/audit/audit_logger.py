import hashlib

from sqlalchemy.orm import Session

from app.db.models import AuditLog


def text_digest(text: str) -> dict:
    return {"summary": text[:200], "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}


def log_action(
    db: Session,
    action: str,
    user_id: str | None = None,
    target_type: str = "",
    target_id: str = "",
    detail: dict | None = None,
    status: str = "success",
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail_json=detail or {},
            status=status,
        )
    )
    db.commit()

