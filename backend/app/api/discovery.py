from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app.api.dependencies import DB, Actor
from app.db.identity import Role, WorkspaceMembership
from app.db.models import Workspace
from app.repositories import discovery
from app.schemas.discovery import DraftListItem, Page, VersionListItem, WorkspaceView
from app.schemas.identity import ProjectInput, ProjectView
from app.services.access import REVIEWERS, audit, require_project

router = APIRouter(tags=["discovery"])
Offset = Annotated[int, Query(ge=0, le=100_000)]
Limit = Annotated[int, Query(ge=1, le=100)]


@router.post("/workspaces", status_code=201)
def create_workspace(body: ProjectInput, identity: Actor, db: DB) -> WorkspaceView:
    workspace = Workspace(name=body.name)
    db.add(workspace)
    db.flush()
    db.add(
        WorkspaceMembership(
            workspace_id=workspace.id, user_id=identity.user.id, role=Role.ADMIN
        )
    )
    audit(db, identity.user.id, "workspace.created", workspace_id=workspace.id)
    db.commit()
    return WorkspaceView(id=workspace.id, name=workspace.name, role=Role.ADMIN)


@router.get("/workspaces")
def my_workspaces(
    identity: Actor,
    db: DB,
    offset: Offset = 0,
    limit: Limit = 25,
) -> Page[WorkspaceView]:
    return discovery.workspaces(db, identity.user.id, offset, limit)


@router.get("/workspaces/{workspace_id}/projects")
def my_projects(
    workspace_id: UUID,
    identity: Actor,
    db: DB,
    offset: Offset = 0,
    limit: Limit = 25,
) -> Page[ProjectView]:
    if db.get(WorkspaceMembership, (workspace_id, identity.user.id)) is None:
        raise HTTPException(404, "Workspace not found")
    return discovery.projects(db, workspace_id, identity.user.id, offset, limit)


@router.get("/projects/{project_id}/drafts")
def review_queue(
    project_id: UUID,
    identity: Actor,
    db: DB,
    offset: Offset = 0,
    limit: Limit = 25,
) -> Page[DraftListItem]:
    access = require_project(db, project_id, identity.user.id)
    access.require(REVIEWERS)
    return discovery.drafts(db, access, offset, limit)


@router.get("/projects/{project_id}/versions")
def approved_versions(
    project_id: UUID,
    identity: Actor,
    db: DB,
    offset: Offset = 0,
    limit: Limit = 25,
) -> Page[VersionListItem]:
    access = require_project(db, project_id, identity.user.id)
    access.require(REVIEWERS | {Role.RECIPIENT})
    return discovery.versions(db, access, offset, limit)
