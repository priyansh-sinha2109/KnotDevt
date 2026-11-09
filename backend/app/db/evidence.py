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


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    current_number: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ClaimRevision(Base):
    __tablename__ = "claim_revisions"
    __table_args__ = (UniqueConstraint("claim_id", "number"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    claim_id: Mapped[UUID] = mapped_column(ForeignKey("claims.id"))
    number: Mapped[int]
    kind: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(24))
    statement: Mapped[str] = mapped_column(Text)
    reviewer_note: Mapped[str | None] = mapped_column(Text)
    authored_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class EvidenceLink(Base):
    __tablename__ = "evidence_links"
    __table_args__ = (
        CheckConstraint(
            "start_offset >= 0 AND end_offset > start_offset", name="valid_span"
        ),
        UniqueConstraint(
            "claim_revision_id",
            "source_revision_id",
            "relation",
            "start_offset",
            "end_offset",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    claim_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("claim_revisions.id"), index=True
    )
    source_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("source_revisions.id"), index=True
    )
    relation: Mapped[str] = mapped_column(String(16))
    start_offset: Mapped[int]
    end_offset: Mapped[int]


class ClaimRelationship(Base):
    __tablename__ = "claim_relationships"
    __table_args__ = (
        CheckConstraint("origin_id <> target_id", name="no_self_relation"),
    )

    origin_id: Mapped[UUID] = mapped_column(ForeignKey("claims.id"), primary_key=True)
    target_id: Mapped[UUID] = mapped_column(
        ForeignKey("claims.id"), primary_key=True, index=True
    )
    relation: Mapped[str] = mapped_column(String(16), primary_key=True)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (UniqueConstraint("job_id", "role", "attempt"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id"), index=True)
    role: Mapped[str] = mapped_column(String(32))
    attempt: Mapped[int]
    model: Mapped[str] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(16))
    output: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(48))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
