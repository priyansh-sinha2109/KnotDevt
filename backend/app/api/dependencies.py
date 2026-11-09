import hmac
from typing import Annotated

from fastapi import Depends, HTTPException, Request
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


def current_identity(request: Request, db: DB) -> Identity:
    identity = authenticate(db, request.cookies.get(COOKIE))
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        verify_origin(request)
        csrf = request.headers.get("X-CSRF-Token", "").encode()
        if not hmac.compare_digest(csrf, identity.csrf.encode()):
            raise HTTPException(403, "Invalid CSRF token")
    return identity


Actor = Annotated[Identity, Depends(current_identity)]
