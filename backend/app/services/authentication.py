import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import HTTPException
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from app.core.cache import redis_client
from app.core.config import settings
from app.db.identity import LoginSession, User
from app.repositories.identity import user_by_email
from app.services.access import audit

COOKIE = "knotdevt_session"
TOKEN = re.compile(r"[A-Za-z0-9_-]{43}\.[a-f0-9]{64}")
SESSION_AGE = timedelta(hours=8)
PASSWORDS = PasswordHasher()


@dataclass(frozen=True)
class Identity:
    user: User
    session: LoginSession
    csrf: str


@lru_cache
def dummy_hash() -> str:
    return PASSWORDS.hash(secrets.token_hex(32))


def mac(value: str) -> str:
    key = settings().session_signing_secret.get_secret_value().encode()
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()


def check_login_limit(client: str) -> None:
    key = f"knotdevt:login:{mac(client)}"
    try:
        count = redis_client().eval(
            "local n = redis.call('INCR', KEYS[1]); "
            "if n == 1 then redis.call('EXPIRE', KEYS[1], 60) end; return n",
            1,
            key,
        )
    except RedisError:
        raise HTTPException(503, "Sign-in temporarily unavailable") from None
    if isinstance(count, int) and count > 30:
        raise HTTPException(
            429, "Too many sign-in attempts", headers={"Retry-After": "60"}
        )


def sign_in(
    db: Session, email: str, password: str, client: str
) -> tuple[str, Identity]:
    check_login_limit(client)
    user = user_by_email(db, email)
    candidate = user.password_hash if user is not None else dummy_hash()
    try:
        PASSWORDS.verify(candidate, password)
    except (VerificationError, InvalidHashError):
        raise HTTPException(401, "Invalid credentials") from None
    if user is None or not user.active:
        raise HTTPException(401, "Invalid credentials")
    if PASSWORDS.check_needs_rehash(candidate):
        user.password_hash = PASSWORDS.hash(password)
    token = secrets.token_urlsafe(32)
    login = LoginSession(
        digest=hashlib.sha256(token.encode()).hexdigest(),
        user_id=user.id,
        expires_at=datetime.now(UTC) + SESSION_AGE,
    )
    db.add(login)
    audit(db, user.id, "session.created")
    db.commit()
    return f"{token}.{mac('session:' + token)}", Identity(
        user, login, mac("csrf:" + token)
    )


def authenticate(db: Session, cookie: str | None) -> Identity:
    denial = HTTPException(401, "Authentication required")
    if cookie is None or not TOKEN.fullmatch(cookie):
        raise denial
    token, signature = cookie.split(".")
    if not hmac.compare_digest(signature, mac("session:" + token)):
        raise denial
    login = db.get(LoginSession, hashlib.sha256(token.encode()).hexdigest())
    if login is None or login.expires_at <= datetime.now(UTC):
        raise denial
    user = db.get(User, login.user_id)
    if user is None or not user.active:
        raise denial
    return Identity(user, login, mac("csrf:" + token))


def sign_out(db: Session, identity: Identity) -> None:
    db.delete(identity.session)
    audit(db, identity.user.id, "session.revoked")
    db.commit()
