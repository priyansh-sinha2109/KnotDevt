from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.identity import Project, ProjectMembership, User, WorkspaceMembership


def user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))


def project_membership(
    db: Session, project_id: UUID, user_id: UUID
) -> tuple[Project, str] | None:
    row = db.execute(
        select(Project, ProjectMembership.role)
        .join(ProjectMembership, ProjectMembership.project_id == Project.id)
        .join(
            WorkspaceMembership,
            (WorkspaceMembership.workspace_id == Project.workspace_id)
            & (WorkspaceMembership.user_id == ProjectMembership.user_id),
        )
        .where(Project.id == project_id, ProjectMembership.user_id == user_id)
    ).one_or_none()
    return (row[0], row[1]) if row else None
