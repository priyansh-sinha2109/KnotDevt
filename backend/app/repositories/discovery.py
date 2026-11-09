from typing import Any
from uuid import UUID

from sqlalchemy import String, cast, exists, func, literal_column, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.selectable import ScalarSelect

from app.db.agent_inputs import AgentRequest
from app.db.handover import Draft, Version, VersionWithdrawal
from app.db.identity import Project, ProjectMembership, Role, WorkspaceMembership
from app.db.models import Workspace
from app.db.sources import Source, SourceRevision
from app.repositories.sources import can_read_source
from app.schemas.discovery import DraftListItem, Page, VersionListItem, WorkspaceView
from app.schemas.identity import ProjectView
from app.services.access import ProjectAccess


def paged[T](rows: list[T], offset: int, limit: int) -> Page[T]:
    return Page(
        items=rows[:limit], next_offset=offset + limit if len(rows) > limit else None
    )


def workspaces(db: Session, user: UUID, offset: int, limit: int) -> Page[WorkspaceView]:
    rows = db.execute(
        select(Workspace.id, Workspace.name, WorkspaceMembership.role)
        .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Workspace.id)
        .where(WorkspaceMembership.user_id == user)
        .order_by(Workspace.id)
        .offset(offset)
        .limit(limit + 1)
    )
    return paged(
        [WorkspaceView(id=r[0], name=r[1], role=Role(r[2])) for r in rows],
        offset,
        limit,
    )


def projects(
    db: Session,
    workspace: UUID,
    user: UUID,
    offset: int,
    limit: int,
) -> Page[ProjectView]:
    rows = db.execute(
        select(Project.id, Project.name, ProjectMembership.role)
        .join(ProjectMembership, ProjectMembership.project_id == Project.id)
        .where(Project.workspace_id == workspace, ProjectMembership.user_id == user)
        .order_by(Project.id)
        .offset(offset)
        .limit(limit + 1)
    )
    return paged(
        [
            ProjectView(id=r[0], workspace_id=workspace, name=r[1], role=Role(r[2]))
            for r in rows
        ],
        offset,
        limit,
    )


def permitted_revisions(access: ProjectAccess) -> ScalarSelect[Any]:
    return (
        select(
            func.coalesce(
                func.jsonb_agg(cast(SourceRevision.id, String)),
                literal_column("'[]'::jsonb"),
            )
        )
        .select_from(SourceRevision)
        .join(Source, Source.id == SourceRevision.source_id)
        .where(Source.project_id == access.project.id, can_read_source(access.user_id))
        .scalar_subquery()
    )


def drafts(
    db: Session,
    access: ProjectAccess,
    offset: int,
    limit: int,
) -> Page[DraftListItem]:
    rows = db.scalars(
        select(Draft)
        .join(AgentRequest, AgentRequest.job_id == Draft.agent_job_id)
        .where(
            Draft.project_id == access.project.id,
            AgentRequest.revision_ids.contained_by(permitted_revisions(access)),
            ~exists().where(
                Version.draft_id == Draft.id,
                Version.draft_revision + 1 == Draft.revision,
            ),
        )
        .order_by(Draft.created_at.desc(), Draft.id)
        .offset(offset)
        .limit(limit + 1)
    )
    return paged(
        [
            DraftListItem(
                id=row.id,
                task=row.task,
                revision=row.revision,
                created_at=row.created_at,
            )
            for row in rows
        ],
        offset,
        limit,
    )


def versions(
    db: Session,
    access: ProjectAccess,
    offset: int,
    limit: int,
) -> Page[VersionListItem]:
    visible = (
        Version.audience.contains([str(access.user_id)])
        if access.role == Role.RECIPIENT
        else Version.id.is_not(None)
    )
    rows = db.scalars(
        select(Version)
        .where(
            Version.project_id == access.project.id,
            visible,
            Version.source_revision_ids.contained_by(permitted_revisions(access)),
            ~exists().where(VersionWithdrawal.version_id == Version.id),
        )
        .order_by(Version.approved_at.desc(), Version.id)
        .offset(offset)
        .limit(limit + 1)
    )
    return paged(
        [
            VersionListItem(
                id=row.id,
                draft_id=row.draft_id,
                number=row.number,
                task=row.task,
                approved_at=row.approved_at,
            )
            for row in rows
        ],
        offset,
        limit,
    )
