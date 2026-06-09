from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.security import create_access_token, decode_access_token, verify_password
from app.db.models import User
from app.db.session import get_db
from app.schemas.auth import LoginRequest
from app.schemas.common import ok
from app.services.audit.audit_logger import log_action

router = APIRouter(prefix="/auth", tags=["auth"])


def serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "department": user.department,
    }


def get_current_user(
    authorization: str | None = Header(default=None), db: Session = Depends(get_db)
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="未登录")
    token = authorization.split(" ", 1)[1]
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="登录已过期")
    user = db.query(User).filter(User.username == payload["sub"], User.is_active.is_(True)).one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")
    return user


@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username, User.is_active.is_(True)).one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        log_action(db, "登录", target_type="user", target_id=payload.username, status="failed")
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token(user.username)
    log_action(db, "登录", user_id=user.id, target_type="user", target_id=user.id)
    return ok({"access_token": token, "token_type": "bearer", "user": serialize_user(user)})


@router.post("/logout")
def logout(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    log_action(db, "登出", user_id=current_user.id, target_type="user", target_id=current_user.id)
    return ok({"status": "logged_out"})


@router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return ok(serialize_user(current_user))

