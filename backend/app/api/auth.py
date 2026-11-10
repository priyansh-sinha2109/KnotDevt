import logging

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy.exc import IntegrityError, OperationalError

from app.api.dependencies import DB, Actor, verify_origin
from app.core.config import settings
from app.db.identity import User
from app.schemas.identity import LoginInput, RegistrationInput, SessionView
from app.services.authentication import (
    COOKIE,
    PASSWORDS,
    SESSION_AGE,
    Identity,
    check_login_limit,
    sign_in,
    sign_out,
)

router = APIRouter(prefix="/auth", tags=["authentication"])
logger = logging.getLogger("uvicorn.error")


def view(identity: Identity) -> SessionView:
    return SessionView(
        user_id=identity.user.id, email=identity.user.email, csrf_token=identity.csrf
    )


@router.post("/register", status_code=204)
def register(data: RegistrationInput, request: Request, db: DB) -> Response:
    verify_origin(request)
    check_login_limit(request.client.host if request.client else "unknown")
    db.add(
        User(
            email=data.email.lower(),
            password_hash=PASSWORDS.hash(data.password.get_secret_value()),
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            409, "Unable to create this account. Try signing in."
        ) from None
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.post("/login")
def login(
    data: LoginInput, request: Request, response: Response, db: DB
) -> SessionView:
    verify_origin(request)
    client = request.client.host if request.client else "unknown"
    try:
        cookie, identity = sign_in(
            db, data.email.lower(), data.password.get_secret_value(), client
        )
    except OperationalError:
        logger.warning(
            "sign_in_database_unavailable request_id=%s", request.state.request_id
        )
        raise HTTPException(503, "Sign-in temporarily unavailable") from None
    response.set_cookie(
        COOKIE,
        cookie,
        max_age=int(SESSION_AGE.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=settings().secure_cookies,
    )
    response.headers["Cache-Control"] = "no-store"
    return view(identity)


@router.get("/me")
def me(identity: Actor, response: Response) -> SessionView:
    response.headers["Cache-Control"] = "no-store"
    return view(identity)


@router.post("/logout", status_code=204)
def logout(identity: Actor, db: DB) -> Response:
    sign_out(db, identity)
    response = Response(status_code=204)
    response.delete_cookie(
        COOKIE, httponly=True, secure=settings().secure_cookies, samesite="lax"
    )
    return response
