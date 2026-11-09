from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Attempt(Base):
    __tablename__ = "readiness_attempts"
    __table_args__ = (
        CheckConstraint("score BETWEEN 0 AND 100", name="valid_readiness_score"),
        UniqueConstraint("rubric_id", "recipient_id", "client_attempt_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    rubric_id: Mapped[UUID] = mapped_column(
        ForeignKey("readiness_rubrics.id"), index=True
    )
    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("handover_versions.id"), index=True
    )
    recipient_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    client_attempt_id: Mapped[UUID | None]
    source_revision_ids: Mapped[list[str]] = mapped_column(JSONB)
    answers: Mapped[dict[str, int]] = mapped_column(JSONB)
    explanation: Mapped[str | None] = mapped_column(Text)
    score: Mapped[int]
    status: Mapped[str] = mapped_column(String(40))
    package_status: Mapped[str] = mapped_column(String(40))
    gates: Mapped[list[str]] = mapped_column(JSONB)
    feedback: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AttemptAdvisory(Base):
    __tablename__ = "attempt_advisories"

    attempt_id: Mapped[UUID] = mapped_column(
        ForeignKey("readiness_attempts.id"), primary_key=True
    )
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id"), unique=True)
    model: Mapped[str] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(24))
    feedback: Mapped[str | None] = mapped_column(Text)


class AttemptReview(Base):
    __tablename__ = "attempt_reviews"

    attempt_id: Mapped[UUID] = mapped_column(
        ForeignKey("readiness_attempts.id"), primary_key=True
    )
    reviewer_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    feedback: Mapped[str] = mapped_column(Text)
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
