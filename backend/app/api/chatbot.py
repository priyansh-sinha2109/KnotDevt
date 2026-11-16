"""Guide chatbot REST endpoints.

Guests (no session cookie) and authenticated users share the message endpoint.
Guests can ask about KnotDevt features and public documentation but cannot
list or retrieve persistent sessions.  All mutations enforce CSRF for
authenticated users via the ``optional_identity`` dependency.
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from redis.exceptions import RedisError

from app.api.dependencies import DB, OptionalActor
from app.core.cache import redis_client
from app.schemas.chatbot import (
    ChatAvailability,
    ChatMessageInput,
    ChatResponse,
    ChatSessionListItem,
    ChatSessionView,
)
from app.services import chatbot
from app.services.authentication import Identity

router = APIRouter(tags=["chatbot"])

CHAT_RATE_LIMIT = 20
CHAT_RATE_WINDOW = 60


def _check_chat_rate_limit(request: Request, identity: Identity | None) -> None:
    """Bound chat message frequency per client to prevent abuse."""
    import hashlib

    client = request.client.host if request.client else "unknown"
    user_key = (
        identity.user.id.hex
        if identity
        else f"guest:{hashlib.sha256(client.encode()).hexdigest()[:16]}"
    )
    key = f"knotdevt:chat:{user_key}"
    try:
        count = redis_client().eval(
            "local n = redis.call('INCR', KEYS[1]); "
            "if n == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end; return n",
            1,
            key,
            str(CHAT_RATE_WINDOW),
        )
    except RedisError:
        # Fail open: allow the message if Redis is unavailable.
        return
    if isinstance(count, int) and count > CHAT_RATE_LIMIT:
        raise HTTPException(
            429,
            "You've sent too many messages. Please wait a moment and try again.",
            headers={"Retry-After": str(CHAT_RATE_WINDOW)},
        )


@router.get("/chatbot/availability")
def availability(identity: OptionalActor, db: DB) -> ChatAvailability:
    """Check whether the AI guide is configured and available."""
    return chatbot.check_availability(db, identity)


@router.post("/chatbot/messages", response_model=ChatResponse)
def send_message(
    body: ChatMessageInput,
    request: Request,
    response: Response,
    identity: OptionalActor,
    db: DB,
) -> ChatResponse:
    """Send a message to the AI guide and receive a response.

    Guests can ask general product questions.  Authenticated users can
    receive page-specific guidance.  Neither can access project data.
    """
    _check_chat_rate_limit(request, identity)
    response.headers["Cache-Control"] = "no-store"
    return chatbot.send_message(db, identity, body)


@router.get("/chatbot/sessions", response_model=list[ChatSessionListItem])
def sessions(identity: OptionalActor, db: DB) -> list[ChatSessionListItem]:
    """List the caller's chat sessions.  Guests receive an empty list."""
    if identity is None:
        return []
    return chatbot.list_sessions(db, identity)


@router.get("/chatbot/sessions/{session_id}", response_model=ChatSessionView)
def session_detail(
    session_id: UUID, identity: OptionalActor, db: DB
) -> ChatSessionView:
    """Retrieve a chat session with its messages.  Enforces ownership."""
    return chatbot.get_session(db, identity, session_id)


@router.delete("/chatbot/sessions/{session_id}", status_code=204)
def session_delete(session_id: UUID, identity: OptionalActor, db: DB) -> Response:
    """Delete a chat session and all its messages.  Enforces ownership."""
    chatbot.delete_session(db, identity, session_id)
    return Response(status_code=204)
