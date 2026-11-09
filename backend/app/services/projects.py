from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.identity import Project, ProjectMembership, Role, User, WorkspaceMembership
from app.services.access import audit, require_workspace_admin


def create_project(db: Session, workspace_id: UUID, actor: UUID, name: str) -> Project:
    require_workspace_admin(db, workspace_id, actor)
    project = Project(workspace_id=workspace_id, name=name)
    db.add(project)
    db.flush()
    db.add(ProjectMembership(project_id=project.id, user_id=actor, role=Role.ADMIN))
    audit(db, actor, "project.created", project=project, target_id=project.id)
    db.commit()
    return project


def set_workspace_role(
    db: Session, workspace_id: UUID, actor: UUID, user_id: UUID, role: Role
) -> None:
    require_workspace_admin(db, workspace_id, actor)
    if actor == user_id:
        raise HTTPException(409, "Cannot change your own workspace role")
    user = db.get(User, user_id)
    if user is None or not user.active:
        raise HTTPException(404, "User not found")
    statement = insert(WorkspaceMembership).values(
        workspace_id=workspace_id, user_id=user_id, role=role
    )
    db.execute(
        statement.on_conflict_do_update(
            index_elements=["workspace_id", "user_id"], set_={"role": role}
        )
    )
    audit(
        db,
        actor,
        "workspace.role_changed",
        workspace_id=workspace_id,
        target_id=user_id,
    )
    db.commit()


def assign_project(
    db: Session, project_id: UUID, actor: UUID, user_id: UUID, role: Role
) -> None:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    require_workspace_admin(db, project.workspace_id, actor)
    if db.get(WorkspaceMembership, (project.workspace_id, user_id)) is None:
        raise HTTPException(404, "Workspace member not found")
    statement = insert(ProjectMembership).values(
        project_id=project_id, user_id=user_id, role=role
    )
    db.execute(
        statement.on_conflict_do_update(
            index_elements=["project_id", "user_id"], set_={"role": role}
        )
    )
    audit(db, actor, "project.role_changed", project=project, target_id=user_id)
    db.commit()
