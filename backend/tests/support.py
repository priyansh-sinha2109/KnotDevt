import time
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.identity import Project, ProjectMembership, Role
from app.db.models import Workspace
from app.db.session import engine
from app.main import app
from tests.integration.test_auth import PASSWORD, create_member

FIXTURES = Path(__file__).parent / "fixtures"


def project_with(*roles: Role) -> tuple[UUID, list[tuple[UUID, str]]]:
    with Session(engine()) as db, db.begin():
        workspace = Workspace(name="Synthetic integration")
        db.add(workspace)
        db.flush()
        project = Project(workspace_id=workspace.id, name="Integration project")
        db.add(project)
        db.flush()
        accounts = []
        for role in roles:
            user = create_member(db, workspace.id, role)
            db.add(ProjectMembership(project_id=project.id, user_id=user.id, role=role))
            accounts.append((user.id, user.email))
        return project.id, accounts


def client_for(email: str) -> TestClient:
    client = TestClient(app, client=(f"test-{uuid4().hex}", 50000))
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return client


def wait_for_job(client: TestClient, job_id: str, timeout: float = 12) -> dict:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        status = client.get(f"/api/v1/jobs/{job_id}")
        assert status.status_code == 200
        if status.json()["state"] != "queued":
            return status.json()
        time.sleep(0.1)
    raise AssertionError("Job did not complete within the test timeout")


def create_demo_draft(
    client: TestClient,
    project: UUID,
    recipient: UUID,
    *,
    extra_import: dict | None = None,
) -> dict:
    from app.workers.celery_app import execute

    prefix = f"/api/v1/projects/{project}"
    for fixture in ("issues", "conversations"):
        response = client.post(
            prefix + "/imports",
            content=(FIXTURES / f"{fixture}.json").read_bytes(),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 202, response.text
        execute(response.json()["id"])
    if extra_import is not None:
        response = client.post(prefix + "/imports", json=extra_import)
        assert response.status_code == 202, response.text
        execute(response.json()["id"])
    response = client.post(
        prefix + "/agent-jobs",
        json={
            "task": "Prepare the event-registration payment release",
            "audience": [str(recipient)],
        },
    )
    assert response.status_code == 202, response.text
    agent_job = response.json()["id"]
    execute(agent_job)
    response = client.post(prefix + "/drafts", json={"agent_job_id": agent_job})
    assert response.status_code == 201, response.text
    return response.json()
