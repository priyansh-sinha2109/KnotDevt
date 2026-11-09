from uuid import UUID

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class AgentRequest(Base):
    __tablename__ = "agent_requests"

    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id"), primary_key=True)
    input: Mapped[dict[str, object]] = mapped_column(JSONB)
    revision_ids: Mapped[list[str]] = mapped_column(JSONB)
    policy_revisions: Mapped[dict[str, int]] = mapped_column(JSONB)
    provider: Mapped[str]
    model: Mapped[str]
    attempt_limit: Mapped[int]
    timeout_seconds: Mapped[int]
    token_limit: Mapped[int]
