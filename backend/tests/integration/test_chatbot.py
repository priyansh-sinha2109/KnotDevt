"""Integration tests for the guide chatbot API.

These tests mock the Gemini provider so no live API calls are made.
They verify guest/authenticated access, CSRF enforcement, session
ownership, error handling, and the OpenAPI schema.
"""

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.db.identity import Role
from app.db.models import Workspace
from app.db.session import engine
from app.main import app
from tests.integration.test_auth import PASSWORD, create_member


def _mock_generate_chat(text: str = "I can help with that."):
    """Return a monkeypatch-compatible replacement for generate_chat."""

    def _mock(system_instruction: str, history: list, **kwargs: object) -> str:
        assert "KnotDevt Guide" in system_instruction
        assert "PRODUCT KNOWLEDGE" in system_instruction
        return text

    return _mock


def _mock_quota_error():
    """Return a replacement that raises a quota-exhausted error."""
    from app.agents.chatbot_provider import ChatQuotaExhausted

    def _mock(system_instruction: str, history: list, **kwargs: object) -> str:
        raise ChatQuotaExhausted("Quota exhausted")

    return _mock


def _create_user(role: Role = Role.REVIEWER) -> str:
    """Create a workspace member and return their email."""
    from sqlalchemy.orm import Session

    with Session(engine()) as db, db.begin():
        workspace = Workspace(name="Chatbot test workspace")
        db.add(workspace)
        db.flush()
        user = create_member(db, workspace.id, role)
        return user.email


def _login(client: TestClient, email: str) -> dict[str, str]:
    """Log in and return CSRF headers."""
    login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert login.status_code == 200, login.text
    return {"X-CSRF-Token": login.json()["csrf_token"]}


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------


def test_guest_availability() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/chatbot/availability")
        assert response.status_code == 200
        data = response.json()
        assert "available" in data
        assert data["mode"] == "guide_guest"


def test_authed_availability() -> None:
    email = _create_user()
    with TestClient(app) as client:
        _login(client, email)
        response = client.get("/api/v1/chatbot/availability")
        assert response.status_code == 200
        assert response.json()["mode"] == "guide"


# ---------------------------------------------------------------------------
# Guest message sending
# ---------------------------------------------------------------------------


def test_guest_can_send_message(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.chatbot.generate_chat",
        _mock_generate_chat("KnotDevt is a platform."),
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chatbot/messages",
            json={"message": "What is KnotDevt?", "page_context": "landing"},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["session_id"]
        assert data["user_message"]["role"] == "user"
        assert data["user_message"]["content"] == "What is KnotDevt?"
        assert data["assistant_message"]["role"] == "assistant"
        assert data["assistant_message"]["content"] == "KnotDevt is a platform."


def test_guest_cannot_list_sessions(monkeypatch: MonkeyPatch) -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/chatbot/sessions")
        assert response.status_code == 200
        assert response.json() == []


# ---------------------------------------------------------------------------
# Authenticated message sending
# ---------------------------------------------------------------------------


def test_authed_csrf_required_for_post(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.chatbot.generate_chat", _mock_generate_chat())
    email = _create_user()
    with TestClient(app) as client:
        _login(client, email)
        # POST without CSRF should fail.
        response = client.post(
            "/api/v1/chatbot/messages",
            json={"message": "Hello", "page_context": "overview"},
        )
        assert response.status_code == 403


def test_authed_can_send_message_with_csrf(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.chatbot.generate_chat", _mock_generate_chat("Hi there.")
    )
    email = _create_user()
    with TestClient(app) as client:
        csrf = _login(client, email)
        response = client.post(
            "/api/v1/chatbot/messages",
            json={"message": "Hello", "page_context": "overview"},
            headers=csrf,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["assistant_message"]["content"] == "Hi there."


# ---------------------------------------------------------------------------
# Session ownership
# ---------------------------------------------------------------------------


def test_authed_can_list_and_get_sessions(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.chatbot.generate_chat", _mock_generate_chat("Answer.")
    )
    email = _create_user()
    with TestClient(app) as client:
        csrf = _login(client, email)
        # Send a message to create a session.
        post = client.post(
            "/api/v1/chatbot/messages",
            json={"message": "Test", "page_context": "projects"},
            headers=csrf,
        )
        assert post.status_code == 200
        session_id = post.json()["session_id"]

        # List sessions.
        listing = client.get("/api/v1/chatbot/sessions")
        assert listing.status_code == 200
        assert len(listing.json()) >= 1
        assert listing.json()[0]["id"] == session_id

        # Get session detail.
        detail = client.get(f"/api/v1/chatbot/sessions/{session_id}")
        assert detail.status_code == 200
        assert len(detail.json()["messages"]) == 2  # user + assistant


def test_cross_user_access_blocked(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.chatbot.generate_chat", _mock_generate_chat("Answer.")
    )
    email_a = _create_user()
    email_b = _create_user()
    with TestClient(app) as client_a, TestClient(app) as client_b:
        csrf_a = _login(client_a, email_a)
        csrf_b = _login(client_b, email_b)
        # User A creates a session.
        post = client_a.post(
            "/api/v1/chatbot/messages",
            json={"message": "Private", "page_context": "review"},
            headers=csrf_a,
        )
        session_id = post.json()["session_id"]
        # User B cannot access it.
        assert client_b.get(f"/api/v1/chatbot/sessions/{session_id}").status_code == 404
        assert (
            client_b.delete(
                f"/api/v1/chatbot/sessions/{session_id}", headers=csrf_b
            ).status_code
            == 404
        )


def test_guest_cannot_access_authed_session(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.chatbot.generate_chat", _mock_generate_chat("Answer.")
    )
    email = _create_user()
    with TestClient(app) as client:
        csrf = _login(client, email)
        post = client.post(
            "/api/v1/chatbot/messages",
            json={"message": "Test", "page_context": "overview"},
            headers=csrf,
        )
        session_id = post.json()["session_id"]
    # Guest cannot access it.
    with TestClient(app) as guest_client:
        assert (
            guest_client.get(f"/api/v1/chatbot/sessions/{session_id}").status_code
            == 404
        )


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_quota_exhausted_returns_error(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.chatbot.generate_chat", _mock_quota_error())
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chatbot/messages",
            json={"message": "Hello", "page_context": "landing"},
        )
        assert response.status_code == 429
        assert "usage limit" in response.json()["message"].lower()
        # The error message should be stored, not a simulated success.
        data = response.json()
        assert "session_id" not in data or "assistant_message" not in data


def test_empty_message_rejected() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chatbot/messages",
            json={"message": "", "page_context": "landing"},
        )
        assert response.status_code == 422


def test_message_too_long_rejected() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chatbot/messages",
            json={"message": "x" * 2001, "page_context": "landing"},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# OpenAPI schema
# ---------------------------------------------------------------------------


def test_chatbot_endpoints_documented() -> None:
    schema = app.openapi()
    chatbot_paths = [p for p in schema["paths"] if "chatbot" in p]
    assert len(chatbot_paths) >= 4
    methods = {method for p in chatbot_paths for method in schema["paths"][p]}
    assert "get" in methods
    assert "post" in methods
    assert "delete" in methods
