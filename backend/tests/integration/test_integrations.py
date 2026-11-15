"""Offline connector regressions; external responses are explicit fixtures."""

from datetime import UTC, datetime

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.identity import Role
from app.db.integrations import Connection
from app.db.session import engine
from app.integrations import providers
from app.services import integrations
from app.workers.connector_app import sync
from tests.support import client_for, project_with


@pytest.fixture
def encryption(monkeypatch):
    monkeypatch.setattr(
        settings(),
        "integration_encryption_key",
        SecretStr(Fernet.generate_key().decode()),
    )


def test_status_is_backend_configuration_and_requires_membership(monkeypatch):
    monkeypatch.setattr(settings(), "github_client_id", "")
    project, [(_, editor)] = project_with(Role.REVIEWER)
    _, [(_, outsider)] = project_with(Role.REVIEWER)
    with client_for(editor) as client:
        result = client.get(f"/api/v1/projects/{project}/integrations")
        assert result.status_code == 200
        assert result.json()["items"][0]["configured"] is False
        assert result.json()["items"][0]["connections"] == []
        assert (
            client.post(
                f"/api/v1/projects/{project}/integrations/github/connect"
            ).status_code
            == 503
        )
        client.headers.pop("X-CSRF-Token")
        assert (
            client.post(
                f"/api/v1/projects/{project}/integrations/github/connect"
            ).status_code
            == 403
        )
    with client_for(outsider) as client:
        assert client.get(f"/api/v1/projects/{project}/integrations").status_code == 404


def test_connector_sync_is_restricted_idempotent_and_disconnect_hides(
    encryption, monkeypatch
):
    project, [(actor, email), (_, recipient)] = project_with(
        Role.REVIEWER, Role.RECIPIENT
    )
    monkeypatch.setattr(
        providers, "resources", lambda *args: [{"id": "123", "name": "owner/repo"}]
    )
    records = [
        {
            "id": "issue:1",
            "text": "Fixture issue, not live provider data",
            "author": "fixture-author",
            "url": "https://github.com/example/example/issues/1",
            "at": "2026-11-15T00:00:00Z",
            "type": "task",
        }
    ]
    monkeypatch.setattr(providers, "fetch_page", lambda *args: (records, {}, True))
    with Session(engine()) as db:
        row = Connection(
            project_id=project,
            owner_id=actor,
            provider="github",
            external_id="installation1",
            name="Fixture installation",
            credential=integrations.encrypt({"access_token": "synthetic-token"}),
            selected_resources=[{"id": "123", "name": "owner/repo"}],
            cursor={},
            next_sync_at=datetime.now(UTC),
        )
        db.add(row)
        db.commit()
        identity = row.id
    sync(str(identity))
    with Session(engine()) as db:
        row = db.get(Connection, identity)
        assert row.status == "synced"
        assert row.imported_count == 1
        row.next_sync_at = datetime.now(UTC)
        db.commit()
    sync(str(identity))
    with client_for(email) as client:
        response = client.get(f"/api/v1/projects/{project}/sources?provider=github")
        assert len(response.json()["items"]) == 1
        source = response.json()["items"][0]
        assert source["policy"] == "restricted"
        assert (
            client.get(f"/api/v1/sources/{source['id']}/revisions").status_code == 200
        )
        tools = client.get(f"/api/v1/projects/{project}/integrations").text
        assert "synthetic-token" not in tools
        assert "credential" not in tools
        assert (
            len(client.get(f"/api/v1/sources/{source['id']}/revisions").json()["items"])
            == 1
        )
        assert (
            client.post(f"/api/v1/integrations/{identity}/disconnect").status_code
            == 204
        )
        assert client.get(f"/api/v1/sources/{source['id']}").status_code == 404
    with client_for(recipient) as client:
        assert (
            client.get(f"/api/v1/projects/{project}/sources?provider=github").json()[
                "items"
            ]
            == []
        )
        assert client.get(f"/api/v1/integrations/{identity}/resources").status_code in (
            403,
            404,
        )
    sync(str(identity))
    with Session(engine()) as db:
        assert db.get(Connection, identity).status == "disconnected"


def test_bad_oauth_and_webhook_are_rejected(encryption, monkeypatch):
    project, [(_, email)] = project_with(Role.REVIEWER)
    monkeypatch.setattr(
        settings(), "github_webhook_secret", SecretStr("fixture-signing-key")
    )
    with client_for(email) as client:
        assert (
            client.get(
                "/api/v1/integrations/github/callback",
                params={"code": "fixture", "state": "x" * 40},
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/api/v1/integrations/webhooks/github", content=b"{}"
            ).status_code
            == 403
        )


def test_plaintext_credentials_are_not_stored(encryption):
    ciphertext = integrations.encrypt({"access_token": "fixture-private-token"})
    assert "fixture-private-token" not in ciphertext
    assert integrations.decrypt(ciphertext)["access_token"] == "fixture-private-token"


def test_adf_keeps_paragraphs_and_lists():
    assert (
        providers.rich_text(
            {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "First"}],
                    },
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "Second"}],
                    },
                ],
            }
        )
        == "First\nSecond\n"
    )


def test_rate_limit_preserves_checkpoint_and_schedules_backoff(encryption, monkeypatch):
    project, [(actor, _)] = project_with(Role.REVIEWER)

    def limited(*args):
        raise providers.RemoteError("rate_limited", "Fixture rate limit", 120)

    monkeypatch.setattr(providers, "resources", limited)
    with Session(engine()) as db:
        row = Connection(
            project_id=project,
            owner_id=actor,
            provider="slack",
            external_id="T-fixture",
            name="Fixture Slack",
            credential=integrations.encrypt({"access_token": "synthetic-token"}),
            selected_resources=[{"id": "C-fixture", "name": "#fixture"}],
            cursor={"page": {"next": "retained-cursor"}},
            next_sync_at=datetime.now(UTC),
        )
        db.add(row)
        db.commit()
        identity = row.id
    sync(str(identity))
    with Session(engine()) as db:
        row = db.get(Connection, identity)
        assert row.status == "rate_limited"
        assert row.cursor["page"]["next"] == "retained-cursor"
        assert (row.next_sync_at - datetime.now(UTC)).total_seconds() > 100


def test_wrong_resource_selection_is_forbidden(encryption, monkeypatch):
    from fastapi import HTTPException

    project, [(actor, _)] = project_with(Role.REVIEWER)
    monkeypatch.setattr(
        providers,
        "resources",
        lambda *args: [{"id": "allowed", "name": "Allowed repository"}],
    )
    with Session(engine()) as db:
        row = Connection(
            project_id=project,
            owner_id=actor,
            provider="github",
            external_id="fixture",
            name="Fixture",
            credential=integrations.encrypt({"access_token": "fixture-token"}),
            selected_resources=[],
            cursor={},
        )
        db.add(row)
        db.commit()
        with pytest.raises(HTTPException) as error:
            integrations.select_resources(db, row, ["unauthorized"])
        assert error.value.status_code == 403


def test_webhook_deduplication_with_valid_signature(encryption, monkeypatch):
    import hashlib
    import hmac
    import json

    monkeypatch.setattr(
        settings(), "slack_signing_secret", SecretStr("fixture-signing")
    )
    import time
    from uuid import uuid4

    raw = json.dumps(
        {
            "event_id": str(uuid4()),
            "team_id": "no-live-team",
            "event": {"type": "message"},
        }
    ).encode()
    stamp = str(int(time.time()))
    signature = (
        "v0="
        + hmac.new(
            b"fixture-signing", b"v0:" + stamp.encode() + b":" + raw, hashlib.sha256
        ).hexdigest()
    )
    _, [(_, email)] = project_with(Role.REVIEWER)
    with client_for(email) as client:
        headers = {"X-Slack-Request-Timestamp": stamp, "X-Slack-Signature": signature}
        first = client.post(
            "/api/v1/integrations/webhooks/slack", content=raw, headers=headers
        )
        assert first.status_code == 200 and first.json()["accepted"]
        second = client.post(
            "/api/v1/integrations/webhooks/slack", content=raw, headers=headers
        )
        assert second.json()["duplicate"]
        headers["X-Slack-Request-Timestamp"] = "1"
        assert (
            client.post(
                "/api/v1/integrations/webhooks/slack", content=raw, headers=headers
            ).status_code
            == 403
        )


def test_oauth_callback_is_bound_single_use_and_encrypts_tokens(
    encryption, monkeypatch
):
    from urllib.parse import parse_qs, urlparse

    monkeypatch.setattr(settings(), "github_client_id", "fixture-app")
    monkeypatch.setattr(
        settings(), "github_client_secret", SecretStr("fixture-client-secret")
    )
    monkeypatch.setattr(
        providers, "exchange", lambda *args: {"access_token": "fixture-private-token"}
    )
    monkeypatch.setattr(
        providers,
        "identities",
        lambda *args: [{"id": "fixture-installation", "name": "Fixture account"}],
    )
    project, [(_, email)] = project_with(Role.REVIEWER)
    with client_for(email) as client:
        result = client.post(f"/api/v1/projects/{project}/integrations/github/connect")
        assert result.status_code == 200
        url = result.json()["authorization_url"]
        assert url.startswith("https://github.com/login/oauth/authorize?")
        state = parse_qs(urlparse(url).query)["state"][0]
        path = f"/api/v1/integrations/github/callback?state={state}&code=fixture"
        result = client.get(path, follow_redirects=False)
        assert result.status_code == 303
        assert f"project={project}" in result.headers["location"]
        assert client.get(path, follow_redirects=False).status_code == 400
        result = client.get(f"/api/v1/projects/{project}/integrations")
        assert "fixture-private-token" not in result.text
        assert result.json()["items"][0]["connections"][0]["status"] == "connected"
