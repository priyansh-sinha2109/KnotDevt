from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.db.identity import Role


class Page[T](BaseModel):
    items: list[T]
    next_offset: int | None


class WorkspaceView(BaseModel):
    id: UUID
    name: str
    role: Role


class DraftListItem(BaseModel):
    id: UUID
    task: str
    revision: int
    created_at: datetime


class VersionListItem(BaseModel):
    id: UUID
    draft_id: UUID
    number: int
    task: str
    approved_at: datetime
