import base64
import hashlib
import hmac
import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import Settings, get_settings


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def get_password_hash(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return f"pbkdf2_sha256${_b64url(salt)}${_b64url(digest)}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, salt_raw, digest_raw = password_hash.split("$", 2)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    salt = _b64url_decode(salt_raw)
    expected = _b64url_decode(digest_raw)
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return hmac.compare_digest(actual, expected)


def create_access_token(
    subject: str,
    settings: Settings | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    settings = settings or get_settings()
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": subject, "exp": int(expire.timestamp())}
    signing_input = ".".join(
        [
            _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8")),
            _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
        ]
    )
    signature = hmac.new(
        settings.secret_key.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256
    ).digest()
    return f"{signing_input}.{_b64url(signature)}"


def decode_access_token(token: str, settings: Settings | None = None) -> dict[str, Any] | None:
    settings = settings or get_settings()
    try:
        header_raw, payload_raw, signature_raw = token.split(".", 2)
        signing_input = f"{header_raw}.{payload_raw}"
        expected = hmac.new(
            settings.secret_key.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(expected, _b64url_decode(signature_raw)):
            return None
        payload = json.loads(_b64url_decode(payload_raw))
        if int(payload.get("exp", 0)) < int(datetime.now(UTC).timestamp()):
            return None
        return payload
    except Exception:
        return None

