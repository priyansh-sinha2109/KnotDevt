from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, StringConstraints
from sqlalchemy import select

from app.api.dependencies import DB, Actor
from app.db.identity import Project, ProjectMembership, Role, User, WorkspaceMembership
from app.repositories.identity import user_by_email
from app.repositories.sources import lock_project
from app.schemas.identity import MembershipView, ProjectInput, ProjectView, RoleInput
from app.services.access import EDITORS, require_project, require_workspace_admin
from app.services.projects import (
    assign_project,
    create_project,
    set_workspace_role,
    unassign_project,
)

router = APIRouter(tags=["projects"])


class RecipientOption(BaseModel):
    id: UUID
    email: str


class RecipientInput(BaseModel):
    email: Annotated[str, StringConstraints(strip_whitespace=True, max_length=254)]


@router.post("/projects/{project_id}/recipients", status_code=201)
def add_recipient(
    project_id: UUID, body: RecipientInput, identity: Actor, db: DB
) -> RecipientOption:
    access = require_project(db, project_id, identity.user.id)
    require_workspace_admin(db, access.project.workspace_id, identity.user.id)
    lock_project(db, project_id)
    user = user_by_email(db, body.email.lower())
    if (
        user is None
        or not user.active
        or db.get(WorkspaceMembership, (access.project.workspace_id, user.id)) is None
    ):
        raise HTTPException(404, "No workspace member has that email")
    existing = db.get(ProjectMembership, (project_id, user.id))
    if existing is not None and existing.role != Role.RECIPIENT:
        raise HTTPException(409, "This person already has a different project role")
    assign_project(db, project_id, identity.user.id, user.id, Role.RECIPIENT)
    return RecipientOption(id=user.id, email=user.email)


@router.get("/projects/{project_id}/recipients")
def recipients(project_id: UUID, identity: Actor, db: DB) -> list[RecipientOption]:
    access = require_project(db, project_id, identity.user.id)
    access.require(EDITORS)
    users = db.scalars(
        select(User)
        .join(ProjectMembership, ProjectMembership.user_id == User.id)
        .join(WorkspaceMembership, WorkspaceMembership.user_id == User.id)
        .where(
            ProjectMembership.project_id == project_id,
            ProjectMembership.role == Role.RECIPIENT,
            WorkspaceMembership.workspace_id == access.project.workspace_id,
            User.active.is_(True),
        )
        .order_by(User.email)
    )
    return [RecipientOption(id=user.id, email=user.email) for user in users]


def project_view(project: Project, role: Role) -> ProjectView:
    return ProjectView(
        id=project.id, workspace_id=project.workspace_id, name=project.name, role=role
    )


@router.post("/workspaces/{workspace_id}/projects", status_code=201)
def create(
    workspace_id: UUID, body: ProjectInput, identity: Actor, db: DB
) -> ProjectView:
    return project_view(
        create_project(db, workspace_id, identity.user.id, body.name), Role.ADMIN
    )


@router.get("/projects/{project_id}")
def get(project_id: UUID, identity: Actor, db: DB) -> ProjectView:
    access = require_project(db, project_id, identity.user.id)
    return project_view(access.project, access.role)


@router.put("/workspaces/{workspace_id}/members/{user_id}")
def workspace_member(
    workspace_id: UUID, user_id: UUID, body: RoleInput, identity: Actor, db: DB
) -> MembershipView:
    set_workspace_role(db, workspace_id, identity.user.id, user_id, body.role)
    return MembershipView(user_id=user_id, role=body.role)


@router.put("/projects/{project_id}/members/{user_id}")
def project_member(
    project_id: UUID, user_id: UUID, body: RoleInput, identity: Actor, db: DB
) -> MembershipView:
    assign_project(db, project_id, identity.user.id, user_id, body.role)
    return MembershipView(user_id=user_id, role=body.role)


@router.delete("/projects/{project_id}/members/{user_id}", status_code=204)
def remove_project_member(
    project_id: UUID, user_id: UUID, identity: Actor, db: DB
) -> None:
    unassign_project(db, project_id, identity.user.id, user_id)
