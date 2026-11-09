from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.identity import Role
from app.db.models import Workspace
from app.db.session import engine
from app.main import app
from tests.integration.test_auth import PASSWORD, create_member


def test_workspace_admin_creates_project_and_adds_member() -> None:
    with Session(engine()) as db, db.begin():
        workspace = Workspace(name="Synthetic admin test")
        another = Workspace(name="Synthetic outsider")
        db.add_all([workspace, another])
        db.flush()
        admin = create_member(db, workspace.id, Role.ADMIN)
        outsider = create_member(db, another.id, Role.CONTRIBUTOR)
        workspace_id, admin_email, user_id = workspace.id, admin.email, outsider.id

    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login", json={"email": admin_email, "password": PASSWORD}
        )
        assert login.status_code == 200
        headers = {"X-CSRF-Token": login.json()["csrf_token"]}
        project = client.post(
            f"/api/v1/workspaces/{workspace_id}/projects",
            json={"name": "Assigned from admin"},
            headers=headers,
        )
        assert project.status_code == 201
        project_id = project.json()["id"]
        assign = f"/api/v1/projects/{project_id}/members/{user_id}"
        assert (
            client.put(
                assign, json={"role": "contributor"}, headers=headers
            ).status_code
            == 404
        )
        workspace_member = f"/api/v1/workspaces/{workspace_id}/members/{user_id}"
        assert (
            client.put(
                workspace_member, json={"role": "contributor"}, headers=headers
            ).status_code
            == 200
        )
        assert (
            client.put(
                assign, json={"role": "contributor"}, headers=headers
            ).status_code
            == 200
        )
