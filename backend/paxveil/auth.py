import hashlib
import hmac
import secrets
from datetime import timedelta

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from paxveil.config import get_settings
from paxveil.db import Session, User, get_db, now


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    result = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600_000).hex()
    return f"pbkdf2_sha256$600000${salt}${result}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        password_hash(password)
        return False
    return hmac.compare_digest(password_hash(password, stored.split("$")[2]), stored)


def new_session(db: DBSession, user: User, response: Response | None = None) -> str:
    token = secrets.token_urlsafe(32)
    db.add(Session(token_hash=digest(token), user_id=user.id, expires_at=now() + timedelta(days=7)))
    db.commit()
    if response:
        response.set_cookie("paxveil_session", token, httponly=True, secure=get_settings().secure_cookies, samesite="lax", max_age=604800, path="/")
    return token


def token_from(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return request.cookies.get("paxveil_session")


def current_user(request: Request, db: DBSession = Depends(get_db)) -> User:
    token = token_from(request)
    if not token:
        raise HTTPException(401, "Войдите в аккаунт")
    session = db.scalar(select(Session).where(Session.token_hash == digest(token), Session.expires_at > now()))
    if not session:
        raise HTTPException(401, "Сессия истекла")
    user = db.get(User, session.user_id)
    if not user:
        raise HTTPException(401, "Аккаунт недоступен")
    return user


def bot_access(request: Request):
    key = get_settings().bot_key
    if not key or not hmac.compare_digest(request.headers.get("x-bot-key", ""), key):
        raise HTTPException(403, "Bot authentication required")


def user_json(user: User):
    return {"id": user.id, "username": user.username, "telegram_id": int(user.telegram_id) if user.telegram_id else None}
