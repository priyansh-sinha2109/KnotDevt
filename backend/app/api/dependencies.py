import hmac
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import database
from app.services.authentication import COOKIE, Identity, authenticate

DB = Annotated[Session, Depends(database)]


def verify_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    expected = f"{request.url.scheme}://{request.url.netloc}"
    if (
        origin is not None
        and origin != expected
        and origin not in settings().allowed_origins
    ):
        raise HTTPException(403, "Untrusted request origin")
    if request.headers.get("sec-fetch-site") == "cross-site" and origin is None:
        raise HTTPException(403, "Untrusted request origin")


def current_identity(
    request: Request,
    db: DB,
    csrf_token: Annotated[
        str | None,
        Header(
            alias="X-CSRF-Token",
            description=(
                "Required for authenticated mutation requests. Use the csrf_token "
                "returned by /api/v1/auth/login or /api/v1/auth/me with the "
                "matching session cookie. Not required for GET, HEAD or OPTIONS."
            ),
        ),
    ] = None,
) -> Identity:
    identity = authenticate(db, request.cookies.get(COOKIE))
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        verify_origin(request)
        csrf = (csrf_token or "").encode()
        if not hmac.compare_digest(csrf, identity.csrf.encode()):
            raise HTTPException(403, "Invalid CSRF token")
    return identity


Actor = Annotated[Identity, Depends(current_identity)]


def optional_identity(
    request: Request,
    db: DB,
    csrf_token: Annotated[
        str | None,
        Header(
            alias="X-CSRF-Token",
            description=(
                "Required for authenticated mutation requests. Use the csrf_token "
                "returned by /api/v1/auth/login or /api/v1/auth/me with the "
                "matching session cookie. Not required for GET, HEAD or OPTIONS."
            ),
        ),
    ] = None,
) -> Identity | None:
    """Resolve the current identity, returning ``None`` for unauthenticated guests.

    CSRF and origin are still enforced for authenticated mutations, but guests
    (no session cookie) are allowed through without a token.
    """
    cookie = request.cookies.get(COOKIE)
    if cookie is None:
        return None
    try:
        identity = authenticate(db, cookie)
    except HTTPException:
        return None
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        verify_origin(request)
        csrf = (csrf_token or "").encode()
        if not hmac.compare_digest(csrf, identity.csrf.encode()):
            raise HTTPException(403, "Invalid CSRF token")
    return identity


OptionalActor = Annotated[Identity | None, Depends(optional_identity)]
