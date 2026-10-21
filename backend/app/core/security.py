import hashlib
import hmac
import secrets

from fastapi import Depends, Request
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import ApiError
from app.core.settings import settings
from app.enums import Role
from app.models import User

SESSION_COOKIE = "session"
_serializer = URLSafeTimedSerializer(settings.secret_key, salt="session")


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    salt, digest = stored.split("$", 1)
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()
    return hmac.compare_digest(candidate, digest)


def make_token(user_id: int) -> str:
    return _serializer.dumps({"uid": user_id})


def read_token(token: str) -> int | None:
    try:
        return _serializer.loads(token, max_age=settings.session_max_age_seconds)["uid"]
    except (BadSignature, KeyError, TypeError):
        return None


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Сессия берётся из cookie либо из заголовка Authorization: Bearer <token>."""
    token = request.cookies.get(SESSION_COOKIE)
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    uid = read_token(token) if token else None
    user = db.get(User, uid) if uid else None
    if user is None:
        raise ApiError(401, "UNAUTHORIZED", "Требуется вход")
    return user


def client_user(user: User = Depends(current_user)) -> User:
    if user.role != Role.CLIENT:
        raise ApiError(403, "FORBIDDEN", "Доступно только клиенту")
    return user


def staff_user(user: User = Depends(current_user)) -> User:
    if user.role != Role.EMPLOYEE:
        raise ApiError(403, "FORBIDDEN", "Доступно только сотруднику банка")
    return user
