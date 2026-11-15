from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class ResourceView(BaseModel):
    id: str
    name: str


class ResourceList(BaseModel):
    items: list[ResourceView]


class ConnectionView(BaseModel):
    id: UUID
    provider: Literal["github", "slack", "jira"]
    name: str
    status: Literal[
        "not_connected",
        "connecting",
        "connected",
        "syncing",
        "synced",
        "rate_limited",
        "needs_reauthorization",
        "permission_denied",
        "sync_failed",
        "disconnected",
    ]
    selected_resources: list[ResourceView]
    last_sync_at: datetime | None
    last_attempt_at: datetime | None
    next_sync_at: datetime | None
    last_error: str | None
    imported_count: int


class ToolView(BaseModel):
    provider: Literal["github", "slack", "jira"]
    configured: bool
    setup_message: str | None
    connections: list[ConnectionView]


class IntegrationList(BaseModel):
    items: list[ToolView]
