from uuid import UUID

from fastapi import APIRouter

from app.api.dependencies import DB, Actor
from app.db.identity import Project, Role
from app.schemas.identity import MembershipView, ProjectInput, ProjectView, RoleInput
from app.services.access import require_project
from app.services.projects import assign_project, create_project, set_workspace_role

router = APIRouter(tags=["projects"])


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
