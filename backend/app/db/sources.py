from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint("project_id", "provider", "kind", "original_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    provider: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(32))
    original_id: Mapped[str] = mapped_column(String(128))
    restricted: Mapped[bool] = mapped_column(Boolean)
    policy_revision: Mapped[int] = mapped_column(Integer, default=1)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SourceAccessRule(Base):
    __tablename__ = "source_access_rules"

    source_id: Mapped[UUID] = mapped_column(ForeignKey("sources.id"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("project_id", "actor_id", "kind", "key"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(32))
    key: Mapped[str | None] = mapped_column(String(128))
    input_hash: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    dispatch_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    error_code: Mapped[str | None] = mapped_column(String(48))


class ImportPayload(Base):
    __tablename__ = "import_jobs"

    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id"), primary_key=True)
    original: Mapped[bytes] = mapped_column(LargeBinary)


class SourceRevision(Base):
    __tablename__ = "source_revisions"
    __table_args__ = (
        UniqueConstraint("source_id", "content_hash"),
        UniqueConstraint("source_id", "ordinal"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("sources.id"), index=True)
    import_job_id: Mapped[UUID] = mapped_column(ForeignKey("import_jobs.job_id"))
    ordinal: Mapped[int]
    content_hash: Mapped[str] = mapped_column(String(64))
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    author: Mapped[str] = mapped_column(String(160))
    reference: Mapped[str] = mapped_column(String(1024))
    event_type: Mapped[str] = mapped_column(String(32))
    excerpt: Mapped[str] = mapped_column(Text)
    related_ids: Mapped[list[str]] = mapped_column(JSONB)


class ImportResult(Base):
    __tablename__ = "import_results"

    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("import_jobs.job_id"), primary_key=True
    )
    revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("source_revisions.id"), primary_key=True
    )
    duplicate: Mapped[bool]
