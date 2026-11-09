"""Create local demonstration users and return the project ID."""

from getpass import getpass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.identity import Project, ProjectMembership, Role, User, WorkspaceMembership
from app.db.models import Workspace
from app.db.session import engine
from app.services.authentication import PASSWORDS

DEMO_NAME = "SoloOne Demo"


def main() -> None:
    password = getpass("Local demo password for the three synthetic accounts: ")
    if not 12 <= len(password) <= 256:
        raise SystemExit("Use a password between 12 and 256 characters")
    with Session(engine()) as db, db.begin():
        workspace = db.scalar(select(Workspace).where(Workspace.name == DEMO_NAME))
        if workspace is not None:
            raise SystemExit("Demo workspace already exists")
        workspace = Workspace(name=DEMO_NAME)
        db.add(workspace)
        db.flush()
        project = Project(workspace_id=workspace.id, name="College event payments")
        db.add(project)
        db.flush()
        project_id = project.id
        for name, role, assigned in [
            ("reviewer", Role.REVIEWER, True),
            ("recipient", Role.RECIPIENT, True),
            ("restricted", Role.RECIPIENT, False),
        ]:
            user = User(
                email=f"{name}@knotdevt.test", password_hash=PASSWORDS.hash(password)
            )
            db.add(user)
            db.flush()
            db.add(
                WorkspaceMembership(
                    workspace_id=workspace.id, user_id=user.id, role=role
                )
            )
            if assigned:
                db.add(
                    ProjectMembership(project_id=project.id, user_id=user.id, role=role)
                )
    print(f"Demo project {project_id}")


if __name__ == "__main__":
    main()
