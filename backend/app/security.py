import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import Request
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.app.core.config import get_settings
from backend.app.models import SessionRecord, User

password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError):
        return False


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def create_session(db: Session, user: User) -> tuple[str, SessionRecord]:
    settings = get_settings()
    raw = secrets.token_urlsafe(32)
    record = SessionRecord(token_hash=_digest(raw), csrf_token=secrets.token_urlsafe(32), user_id=user.id, expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.session_ttl_hours))
    db.add(record)
    db.commit()
    db.refresh(record)
    return raw, record


def current_session(request: Request, db: Session) -> tuple[User, SessionRecord] | None:
    raw = request.cookies.get(get_settings().session_cookie_name)
    if not raw:
        return None
    record = db.scalar(select(SessionRecord).where(SessionRecord.token_hash == _digest(raw)))
    if not record:
        return None
    expires_at = record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc) or not record.user.is_active:
        return None
    return record.user, record
