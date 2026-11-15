"""Pydantic schemas for the guide chatbot REST API."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints

from app.schemas.sources import StrictModel

# Maximum number of prior turns sent to the model as context.
CHAT_HISTORY_LIMIT = 10
# Maximum message length accepted from the client.
ChatText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]
# Short page-context identifier (e.g. "landing", "projects", "review").
PageContext = Annotated[str, StringConstraints(strip_whitespace=True, max_length=64)]


class ChatMessageInput(StrictModel):
    message: ChatText
    page_context: PageContext | None = None
    session_id: UUID | None = None


class ChatMessageView(BaseModel):
    id: UUID
    role: str
    content: str
    error_code: str | None = None
    created_at: datetime


class ChatSessionView(BaseModel):
    id: UUID
    page_context: str | None = None
    created_at: datetime
    messages: list[ChatMessageView] = Field(default_factory=list)


class ChatSessionListItem(BaseModel):
    id: UUID
    page_context: str | None = None
    created_at: datetime
    message_count: int


class ChatResponse(BaseModel):
    """Full response returned after sending a message."""

    session_id: UUID
    user_message: ChatMessageView
    assistant_message: ChatMessageView


class ChatAvailability(BaseModel):
    """Whether the AI guide is available, with a reason if not."""

    available: bool
    mode: str  # "guide" or "guide_guest"
    reason: str | None = None
