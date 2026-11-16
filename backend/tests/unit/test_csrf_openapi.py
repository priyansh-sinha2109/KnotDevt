from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api import dependencies
from app.api.dependencies import Actor
from app.main import create_app
from app.services.authentication import COOKIE


def test_workspace_openapi_documents_csrf_header() -> None:
    schema = create_app().openapi()
    for path, methods in schema["paths"].items():
        for method, operation in methods.items():
            if method not in {"post", "put", "patch", "delete"}:
                continue
            if path in {"/api/v1/auth/login", "/api/v1/auth/register"}:
                continue
            if path == "/api/v1/integrations/webhooks/{provider}":
                # Provider callbacks use verified HMACs, not browser sessions.
                # Invalid signatures and replay protection have dedicated tests.
                continue
            headers = [
                p
                for p in operation.get("parameters", [])
                if p["in"] == "header" and p["name"] == "X-CSRF-Token"
            ]
            assert len(headers) == 1, (method, path)
            # Optional in the shared dependency so runtime keeps returning 403
            # for missing mutation tokens and GET requests need no token.
            assert headers[0]["required"] is False
    assert "X-CSRF-Token" in str(
        schema["paths"]["/api/v1/workspaces"]["post"]["parameters"]
    )


@pytest.mark.parametrize(
    ("session", "token", "origin", "expected"),
    [
        (False, "matching-token", None, 401),
        (True, None, None, 403),
        (True, "incorrect", None, 403),
        (True, "matching-token", "https://untrusted.invalid", 403),
        (True, "matching-token", "http://localhost:3000", 200),
    ],
)
def test_header_declaration_preserves_runtime_guards(
    monkeypatch, session, token, origin, expected
) -> None:
    identity = SimpleNamespace(csrf="matching-token")

    def authenticate(db, cookie):
        if cookie != "synthetic-session":
            raise HTTPException(401, "Authentication required")
        return identity

    monkeypatch.setattr(dependencies, "authenticate", authenticate)
    app = FastAPI()
    app.dependency_overrides[dependencies.database] = lambda: object()

    @app.post("/mutation")
    @app.get("/mutation")
    def mutation(actor: Actor):
        assert actor is identity
        return {"ok": True}

    with TestClient(app) as client:
        if session:
            client.cookies.set(COOKIE, "synthetic-session")
        headers = {}
        if token is not None:
            headers["X-CSRF-Token"] = token
        if origin is not None:
            headers["Origin"] = origin
        assert client.post("/mutation", headers=headers).status_code == expected
        if session:
            assert client.get("/mutation").status_code == 200
