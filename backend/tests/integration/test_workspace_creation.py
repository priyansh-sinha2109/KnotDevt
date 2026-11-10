from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.identity import Role
from app.main import app
from tests.support import client_for, project_with


def test_registration_has_no_inherited_access() -> None:
    body = {
        "email": f"{uuid4().hex}@test.invalid",
        "password": "synthetic-registration-only",
    }
    with TestClient(app, client=(uuid4().hex, 50000)) as client:
        assert (
            client.post(
                "/api/v1/auth/register",
                json=body,
                headers={"Origin": "https://evil.invalid"},
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/v1/auth/register", json=body | {"password": "short"}
            ).status_code
            == 422
        )
        assert client.post("/api/v1/auth/register", json=body).status_code == 204
        assert client.post("/api/v1/auth/register", json=body).status_code == 409
        assert client.get("/api/v1/auth/me").status_code == 401
        assert client.post("/api/v1/auth/login", json=body).status_code == 200
        assert client.get("/api/v1/workspaces").json()["items"] == []


def test_workspace_creation_is_private_and_requires_csrf() -> None:
    _, [(_, owner), (_, outsider)] = project_with(Role.RECIPIENT, Role.RECIPIENT)
    with TestClient(app) as anonymous:
        assert (
            anonymous.post("/api/v1/workspaces", json={"name": "Private"}).status_code
            == 401
        )
    with client_for(owner) as client, client_for(outsider) as other:
        assert (
            client.post(
                "/api/v1/workspaces",
                json={"name": "Private"},
                headers={"X-CSRF-Token": ""},
            ).status_code
            == 403
        )
        result = client.post("/api/v1/workspaces", json={"name": "Private"})
        assert result.status_code == 201
        workspace = result.json()
        assert workspace["role"] == "administrator"
        path = f"/api/v1/workspaces/{workspace['id']}/projects"
        assert other.get(path).status_code == 404
        assert other.post(path, json={"name": "Denied"}).status_code == 404
        assert client.post(path, json={"name": "First project"}).status_code == 201


def test_recipient_assignment_is_limited_to_workspace_members() -> None:
    project, [(_, owner), (_, reviewer)] = project_with(Role.ADMIN, Role.REVIEWER)
    _, [(_, outsider)] = project_with(Role.RECIPIENT)
    path = f"/api/v1/projects/{project}/recipients"
    with client_for(owner) as admin, client_for(reviewer) as editor:
        assert admin.get(path).json() == []
        assert editor.post(path, json={"email": outsider}).status_code == 403
        assert admin.post(path, json={"email": outsider}).status_code == 404
        assert admin.post(path, json={"email": reviewer}).status_code == 409
        workspace = admin.get(f"/api/v1/projects/{project}").json()["workspace_id"]
        with client_for(outsider) as member:
            assert member.get(path).status_code == 404
            user = member.get("/api/v1/auth/me").json()["user_id"]
            assert (
                admin.put(
                    f"/api/v1/workspaces/{workspace}/members/{user}",
                    json={"role": "recipient"},
                ).status_code
                == 200
            )
            assert admin.post(path, json={"email": outsider}).status_code == 201
            assert editor.get(path).json() == [{"id": user, "email": outsider}]
            assert member.get(path).status_code == 403


def test_invitation_can_be_redeemed_once_by_the_intended_account() -> None:
    project, [(_, owner), (_, reviewer)] = project_with(Role.ADMIN, Role.REVIEWER)
    _, [(_, incoming)] = project_with(Role.RECIPIENT)
    issue = f"/api/v1/projects/{project}/invitations"
    redeem = "/api/v1/invitations/redeem"
    with (
        client_for(owner) as admin,
        client_for(reviewer) as wrong,
        client_for(incoming) as invited,
    ):
        assert wrong.post(issue, json={"email": incoming}).status_code == 403
        created = admin.post(issue, json={"email": incoming})
        assert created.status_code == 201
        body = {"code": created.json()["code"]}
        assert wrong.post(redeem, json=body).status_code == 404
        assert invited.get(f"/api/v1/projects/{project}").status_code == 404
        assert (
            invited.post(redeem, json=body, headers={"X-CSRF-Token": ""}).status_code
            == 403
        )
        result = invited.post(redeem, json=body)
        assert result.status_code == 200
        assert result.json()["role"] == "recipient"
        assert invited.post(redeem, json=body).status_code == 404
        assert invited.get(f"/api/v1/projects/{project}").status_code == 200
