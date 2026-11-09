from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Draft(Base):
    __tablename__ = "handover_drafts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    agent_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_requests.job_id"), unique=True
    )
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    revision: Mapped[int] = mapped_column(default=1)
    task: Mapped[str]
    audience: Mapped[list[str]] = mapped_column(JSONB)
    unresolved: Mapped[list[str]] = mapped_column(JSONB)
    proposed_rubric: Mapped[dict[str, object]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DraftClaim(Base):
    __tablename__ = "draft_claims"
    __table_args__ = (UniqueConstraint("draft_id", "position"),)

    draft_id: Mapped[UUID] = mapped_column(
        ForeignKey("handover_drafts.id"), primary_key=True
    )
    claim_id: Mapped[UUID] = mapped_column(ForeignKey("claims.id"), primary_key=True)
    position: Mapped[int]
    flags: Mapped[list[str]] = mapped_column(JSONB)


class Version(Base):
    __tablename__ = "handover_versions"
    __table_args__ = (
        UniqueConstraint("draft_id", "number"),
        UniqueConstraint("draft_id", "content_hash"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    draft_id: Mapped[UUID] = mapped_column(ForeignKey("handover_drafts.id"), index=True)
    resume_job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id"), unique=True)
    number: Mapped[int]
    draft_revision: Mapped[int]
    approved_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    content_hash: Mapped[str] = mapped_column(String(64))
    task: Mapped[str]
    audience: Mapped[list[str]] = mapped_column(JSONB)
    source_revision_ids: Mapped[list[str]] = mapped_column(JSONB)
    source_policy_revisions: Mapped[dict[str, int]] = mapped_column(JSONB)
    unresolved: Mapped[list[str]] = mapped_column(JSONB)
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class VersionClaim(Base):
    __tablename__ = "version_claims"
    __table_args__ = (UniqueConstraint("version_id", "position"),)

    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("handover_versions.id"), primary_key=True
    )
    claim_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("claim_revisions.id"), primary_key=True, index=True
    )
    position: Mapped[int]


class VersionWithdrawal(Base):
    __tablename__ = "version_withdrawals"

    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("handover_versions.id"), primary_key=True
    )
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Rubric(Base):
    __tablename__ = "readiness_rubrics"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("handover_versions.id"), unique=True
    )
    spec: Mapped[dict[str, object]] = mapped_column(JSONB)
