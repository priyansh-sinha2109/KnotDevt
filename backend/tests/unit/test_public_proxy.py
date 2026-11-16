from fastapi.testclient import TestClient

from scripts.oauth_proxy import app


def test_proxy_denies_private_routes_and_docs() -> None:
    client = TestClient(app)
    for path in ("/docs", "/openapi.json", "/api/v1/projects/1", "/api/v1/admin"):
        assert client.get(path).status_code == 404


def test_proxy_allows_only_provider_callback_and_webhook_paths(monkeypatch) -> None:
    seen: list[tuple[str, str]] = []

    class FakeResponse:
        status_code = 303
        content = b""
        headers = {
            "location": "http://localhost:3000/app",
            "content-type": "text/plain",
        }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def request(self, method, url, **kwargs):
            seen.append((method, url))
            return FakeResponse()

    monkeypatch.setattr(
        "scripts.oauth_proxy.httpx.AsyncClient", lambda **kwargs: FakeClient()
    )
    client = TestClient(app, follow_redirects=False)
    assert (
        client.get(
            "/api/v1/integrations/github/callback?state=x&code=y"
        ).status_code
        == 303
    )
    assert (
        client.post("/api/v1/integrations/webhooks/slack", content=b"{}").status_code
        == 303
    )
    assert (
        client.get(
            "/api/v1/integrations/discord/callback?state=x&code=y"
        ).status_code
        == 404
    )
    assert seen == [
        ("GET", "http://127.0.0.1:8080/api/v1/integrations/github/callback"),
        ("POST", "http://127.0.0.1:8080/api/v1/integrations/webhooks/slack"),
    ]


def test_proxy_rejects_oversized_webhook() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/integrations/webhooks/github", content=b"x" * (1_048_577)
    )
    assert response.status_code == 413
