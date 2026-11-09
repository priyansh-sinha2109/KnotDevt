from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import ColumnElement, delete, func, literal_column, or_, select
from sqlalchemy.orm import Session

from app.db.sources import Source, SourceAccessRule, SourceRevision
from app.repositories.identity import project_membership
from app.repositories.sources import can_read_source, current_revision_id, lock_project
from app.schemas.sources import SourcePolicy, SourcesPage, SourceView
from app.services.access import EDITORS, ProjectAccess, audit, require_project


def source_view(source: Source, revision: SourceRevision) -> SourceView:
    return SourceView(
        id=source.id,
        revision_id=revision.id,
        original_id=source.original_id,
        provider=source.provider,
        kind=source.kind,
        event_type=revision.event_type,
        policy="restricted" if source.restricted else "project",
        content_hash=revision.content_hash,
        author=revision.author,
        reference=revision.reference,
        excerpt=revision.excerpt,
        event_at=revision.event_at,
        imported_at=revision.imported_at,
    )


def list_sources(
    db: Session,
    access: ProjectAccess,
    offset: int,
    limit: int,
    query: str | None = None,
) -> SourcesPage:
    statement = (
        select(Source, SourceRevision)
        .join(SourceRevision, SourceRevision.id == current_revision_id())
        .where(Source.project_id == access.project.id, can_read_source(access.user_id))
    )
    if query:
        english: ColumnElement[str] = literal_column("'english'::regconfig")
        statement = statement.where(
            or_(
                Source.original_id == query,
                func.to_tsvector(english, SourceRevision.excerpt).bool_op("@@")(
                    func.websearch_to_tsquery(english, query)
                ),
            )
        )
    rows = db.execute(
        statement.order_by(Source.id).offset(offset).limit(limit + 1)
    ).all()
    return SourcesPage(
        items=[source_view(row[0], row[1]) for row in rows[:limit]],
        next_offset=offset + limit if len(rows) > limit else None,
    )


def source_context(
    db: Session, source_id: UUID, user_id: UUID
) -> tuple[Source, ProjectAccess]:
    source = db.scalar(
        select(Source)
        .where(Source.id == source_id, can_read_source(user_id))
        .execution_options(populate_existing=True)
    )
    if source is None:
        raise HTTPException(404, "Source not found")
    try:
        access = require_project(db, source.project_id, user_id)
    except HTTPException:
        raise HTTPException(404, "Source not found") from None
    return source, access


def manage_source(
    db: Session, source_id: UUID, user_id: UUID, policy: SourcePolicy | None
) -> None:
    source, _ = source_context(db, source_id, user_id)
    lock_project(db, source.project_id)
    source, access = source_context(db, source_id, user_id)
    access.require(EDITORS)
    if source.owner_id != user_id:
        raise HTTPException(403, "Source policy change is forbidden")
    if policy is None:
        source.deleted_at = datetime.now(UTC)
        action = "source.deleted"
    else:
        desired = (
            policy.allowed_users | {user_id} if policy.policy == "restricted" else set()
        )
        for allowed_user in desired:
            if project_membership(db, access.project.id, allowed_user) is None:
                raise HTTPException(422, "Source allowlist requires project members")
        restricted = policy.policy == "restricted"
        previous = set(
            db.scalars(
                select(SourceAccessRule.user_id).where(
                    SourceAccessRule.source_id == source_id
                )
            )
        )
        if source.restricted == restricted and desired == previous:
            return
        source.restricted = restricted
        db.execute(
            delete(SourceAccessRule).where(SourceAccessRule.source_id == source_id)
        )
        db.add_all(
            SourceAccessRule(source_id=source_id, user_id=allowed_user)
            for allowed_user in desired
        )
        action = "source.policy_changed"
    source.policy_revision += 1
    audit(db, user_id, action, project=access.project, target_id=source.id)
    db.commit()
