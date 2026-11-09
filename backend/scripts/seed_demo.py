"""Create or rotate a synthetic workspace in the dedicated local database."""

import os
from getpass import getpass
from uuid import UUID

from argon2.exceptions import VerificationError
from dotenv import dotenv_values
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import ROOT
from app.db.identity import Project, ProjectMembership, Role, User, WorkspaceMembership
from app.db.models import Workspace
from app.db.session import engine
from app.repositories.identity import user_by_email
from app.services.authentication import PASSWORDS

DEMO_NAME = "SoloOne Demo"
DEMO_ROLES = {
    "reviewer": Role.REVIEWER,
    "recipient": Role.RECIPIENT,
    "restricted": Role.RECIPIENT,
}


def demo_password() -> str:
    password = os.environ.get("KNOTDEVT_DEMO_PASSWORD") or dotenv_values(
        ROOT / ".env"
    ).get("KNOTDEVT_DEMO_PASSWORD")
    if not password:
        password = getpass("Password for the three local synthetic accounts: ")
    if not 12 <= len(password) <= 256:
        raise SystemExit("Use a demo password between 12 and 256 characters")
    return password


def seed(password: str, *, reset: bool = False) -> UUID:
    database = engine()
    if (database.url.host, database.url.port, database.url.database) != (
        "127.0.0.1",
        55432,
        "knotdevt",
    ):
        raise SystemExit("Demo setup requires the dedicated local knotdevt database")
    with Session(database) as db, db.begin():
        current = db.scalars(
            select(Workspace).where(Workspace.name == DEMO_NAME).with_for_update()
        ).one_or_none()
        if current is not None and not reset:
            raise SystemExit("Demo workspace already exists. Use scripts.reset_demo.")
        members = {}
        for name in DEMO_ROLES:
            email = f"{name}@knotdevt.test"
            user = user_by_email(db, email)
            if user is None:
                user = User(email=email, password_hash=PASSWORDS.hash(password))
                db.add(user)
                db.flush()
            else:
                try:
                    PASSWORDS.verify(user.password_hash, password)
                except VerificationError:
                    raise SystemExit(
                        "Use the existing synthetic account password"
                    ) from None
            members[name] = user.id
        if current is not None:
            archive_demo(db, current, set(members.values()))

        workspace = Workspace(name=DEMO_NAME)
        db.add(workspace)
        db.flush()
        project = Project(workspace_id=workspace.id, name="College event payments")
        db.add(project)
        db.flush()
        project_id = project.id
        for name, user_id in members.items():
            role = DEMO_ROLES[name]
            db.add(
                WorkspaceMembership(
                    workspace_id=workspace.id, user_id=user_id, role=role
                )
            )
            if name != "restricted":
                db.add(
                    ProjectMembership(project_id=project_id, user_id=user_id, role=role)
                )
    return project_id


def archive_demo(db: Session, workspace: Workspace, demo_users: set[UUID]) -> None:
    assigned = set(
        db.scalars(
            select(WorkspaceMembership.user_id).where(
                WorkspaceMembership.workspace_id == workspace.id
            )
        )
    )
    if assigned != demo_users:
        raise SystemExit(
            "Workspace membership differs from the synthetic demo. Reset refused."
        )
    projects = select(Project.id).where(Project.workspace_id == workspace.id)
    db.execute(
        delete(ProjectMembership).where(
            ProjectMembership.project_id.in_(projects),
            ProjectMembership.user_id.in_(demo_users),
        )
    )
    db.execute(
        delete(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == workspace.id,
            WorkspaceMembership.user_id.in_(demo_users),
        )
    )
    workspace.name = f"Archived SoloOne demo {workspace.id}"


if __name__ == "__main__":
    print(f"Demo project {seed(demo_password())}")
