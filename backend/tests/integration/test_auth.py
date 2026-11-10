from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db.identity import (
    LoginSession,
    Project,
    ProjectMembership,
    Role,
    User,
    WorkspaceMembership,
)
from app.db.models import Workspace
from app.db.session import engine
from app.main import app
from app.services import authentication
from app.services.authentication import COOKIE, PASSWORDS

PASSWORD = "synthetic-test-only"


def test_login_reports_database_connection_failure(monkeypatch: MonkeyPatch) -> None:
    def unavailable(_db: Session, _email: str) -> User | None:
        raise OperationalError(None, None, TimeoutError("simulated connection timeout"))

    monkeypatch.setattr(authentication, "check_login_limit", lambda _client: None)
    monkeypatch.setattr(authentication, "user_by_email", unavailable)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/login",
            headers={"Origin": "http://localhost:3000"},
            json={"email": "reviewer@test.invalid", "password": PASSWORD},
        )
    assert response.status_code == 503
    assert response.json()["message"] == "Sign-in temporarily unavailable"
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert response.json()["request_id"] == response.headers["x-request-id"]
    assert "set-cookie" not in response.headers


def create_member(db: Session, workspace_id: UUID, role: Role) -> User:
    user = User(
        email=f"{uuid4().hex}@test.invalid", password_hash=PASSWORDS.hash(PASSWORD)
    )
    db.add(user)
    db.flush()
    db.add(WorkspaceMembership(workspace_id=workspace_id, user_id=user.id, role=role))
    return user


def test_session_lifecycle_and_csrf() -> None:
    with Session(engine()) as db, db.begin():
        workspace = Workspace(name="Synthetic auth test")
        db.add(workspace)
        db.flush()
        email = create_member(db, workspace.id, Role.REVIEWER).email

    with TestClient(app) as client:
        assert client.get("/api/v1/auth/me").status_code == 401
        login = client.post(
            "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
        )
        assert login.status_code == 200, login.text
        cookie = login.cookies[COOKIE]
        assert "HttpOnly" in login.headers["set-cookie"]
        assert "SameSite=lax" in login.headers["set-cookie"]
        assert client.post("/api/v1/auth/logout").status_code == 403
        csrf = {"X-CSRF-Token": login.json()["csrf_token"]}
        assert (
            client.post(
                "/api/v1/auth/logout",
                headers=csrf | {"Origin": "https://other.invalid"},
            ).status_code
            == 403
        )
        assert client.get("/api/v1/auth/me").json()["email"] == email
        assert client.post("/api/v1/auth/logout", headers=csrf).status_code == 204
        assert (
            client.get(
                "/api/v1/auth/me", headers={"Cookie": f"{COOKIE}={cookie}"}
            ).status_code
            == 401
        )


def test_cross_workspace_and_role_escalation() -> None:
    with Session(engine()) as db, db.begin():
        workspace = Workspace(name="Synthetic A")
        other = Workspace(name="Synthetic B")
        db.add_all([workspace, other])
        db.flush()
        viewer = create_member(db, workspace.id, Role.RECIPIENT)
        lead = create_member(db, workspace.id, Role.ADMIN)
        project = Project(name="Assigned", workspace_id=workspace.id)
        hidden = Project(name="Hidden", workspace_id=other.id)
        db.add_all([project, hidden])
        db.flush()
        db.add(
            ProjectMembership(
                project_id=project.id, user_id=viewer.id, role=Role.RECIPIENT
            )
        )
        email, admin_email = viewer.email, lead.email
        member_id, project_id, other_id = (
            str(viewer.id),
            str(project.id),
            str(hidden.id),
        )

    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
        )
        assert login.status_code == 200
        csrf = {"X-CSRF-Token": login.json()["csrf_token"]}
        assert (
            client.get(f"/api/v1/projects/{project_id}").json()["role"] == "recipient"
        )
        assert client.get(f"/api/v1/projects/{other_id}").status_code == 404
        path = f"/api/v1/projects/{project_id}/members/{member_id}"
        assert (
            client.put(path, json={"role": "administrator"}, headers=csrf).status_code
            == 403
        )
        admin = client.post(
            "/api/v1/auth/login", json={"email": admin_email, "password": PASSWORD}
        )
        assert admin.status_code == 200
        assert (
            client.put(
                path,
                json={"role": "reviewer"},
                headers={"X-CSRF-Token": admin.json()["csrf_token"]},
            ).status_code
            == 200
        )


def test_expired_session_and_bad_password() -> None:
    with Session(engine()) as db, db.begin():
        workspace = Workspace(name="Synthetic expiration")
        db.add(workspace)
        db.flush()
        member = create_member(db, workspace.id, Role.RECIPIENT)
        email, member_id = member.email, member.id

    with TestClient(app) as client:
        body = {"email": email, "password": "incorrect"}
        assert client.post("/api/v1/auth/login", json=body).status_code == 401
        assert (
            client.post(
                "/api/v1/auth/login", json=body | {"password": PASSWORD}
            ).status_code
            == 200
        )
        with Session(engine()) as db, db.begin():
            session = db.scalars(
                select(LoginSession).where(LoginSession.user_id == member_id)
            ).one()
            session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        assert client.get("/api/v1/auth/me").status_code == 401
