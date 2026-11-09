from uuid import UUID

from sqlalchemy import ColumnElement, exists, select
from sqlalchemy.orm import Session

from app.db.identity import Project
from app.db.sources import Source, SourceAccessRule, SourceRevision


def can_read_source(user_id: UUID) -> ColumnElement[bool]:
    return Source.deleted_at.is_(None) & (
        Source.restricted.is_(False)
        | exists().where(
            SourceAccessRule.source_id == Source.id, SourceAccessRule.user_id == user_id
        )
    )


def current_revision_id() -> ColumnElement[UUID]:
    return (
        select(SourceRevision.id)
        .where(SourceRevision.source_id == Source.id)
        .order_by(SourceRevision.ordinal.desc())
        .limit(1)
        .correlate(Source)
        .scalar_subquery()
    )


def latest_revision(db: Session, source_id: UUID) -> SourceRevision | None:
    return db.scalar(
        select(SourceRevision)
        .where(SourceRevision.source_id == source_id)
        .order_by(SourceRevision.ordinal.desc())
        .limit(1)
    )


def lock_project(db: Session, project_id: UUID) -> None:
    db.execute(select(Project.id).where(Project.id == project_id).with_for_update())
