from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.identity import AuditEvent, Project, Role, WorkspaceMembership
from app.repositories.identity import project_membership

EDITORS = frozenset({Role.ADMIN, Role.REVIEWER, Role.CONTRIBUTOR})
REVIEWERS = frozenset({Role.ADMIN, Role.REVIEWER})


@dataclass(frozen=True)
class ProjectAccess:
    project: Project
    user_id: UUID
    role: Role

    def require(self, roles: frozenset[Role]) -> None:
        if self.role not in roles:
            raise HTTPException(403, "Project operation is forbidden")


def require_project(db: Session, project_id: UUID, user_id: UUID) -> ProjectAccess:
    membership = project_membership(db, project_id, user_id)
    if membership is None:
        raise HTTPException(404, "Project not found")
    project, role = membership
    db.execute(
        text("SELECT set_config('knotdevt.project_id', :project_id, true)"),
        {"project_id": str(project_id)},
    )
    return ProjectAccess(project, user_id, Role(role))


def require_workspace_admin(db: Session, workspace_id: UUID, user_id: UUID) -> None:
    member = db.get(WorkspaceMembership, (workspace_id, user_id))
    if member is None:
        raise HTTPException(404, "Workspace not found")
    if member.role != Role.ADMIN:
        raise HTTPException(403, "Workspace operation is forbidden")


def audit(
    db: Session,
    actor_id: UUID,
    action: str,
    *,
    project: Project | None = None,
    workspace_id: UUID | None = None,
    target_id: UUID | None = None,
) -> None:
    db.add(
        AuditEvent(
            actor_id=actor_id,
            action=action,
            workspace_id=project.workspace_id if project else workspace_id,
            project_id=project.id if project else None,
            target_id=target_id,
        )
    )
