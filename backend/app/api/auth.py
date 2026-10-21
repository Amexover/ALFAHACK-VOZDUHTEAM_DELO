from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import ApiError
from app.core.security import SESSION_COOKIE, current_user, make_token, verify_password
from app.core.settings import settings
from app.models import User
from app.schemas import LoginIn

router = APIRouter(prefix="/auth", tags=["auth"])


def user_view(u: User) -> dict:
    return {"id": u.id, "login": u.login, "full_name": u.full_name, "first_name": u.first_name, "role": u.role}


@router.post("/login")
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.login == body.login.strip().lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise ApiError(401, "INVALID_CREDENTIALS", "Неверный логин или пароль")
    token = make_token(user.id)
    response.set_cookie(SESSION_COOKIE, token, max_age=settings.session_max_age_seconds, httponly=True,
                        secure=settings.cookie_secure, samesite=settings.cookie_samesite)
    return {"user": user_view(user), "token": token}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"user": user_view(user)}
