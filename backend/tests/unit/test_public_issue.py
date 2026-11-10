import httpx
import pytest
from fastapi import HTTPException

from app.services.github_issue import public_issue


def test_public_issue_uses_fixed_api_and_preserves_body(monkeypatch) -> None:
    body = "## Pending checks\r\nLiteral <script> untrusted body\n"

    def respond(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.github.com/repos/wala/WALA/issues/2119"
        assert "Authorization" not in request.headers
        return httpx.Response(
            200,
            json={
                "number": 2119,
                "title": "Dependency Dashboard",
                "user": {"login": "renovate[bot]"},
                "state": "open",
                "state_reason": None,
                "assignees": [{"login": "liblit"}],
                "closed_at": None,
                "body": body,
                "created_at": "2026-11-06T16:26:27Z",
                "updated_at": "2026-11-10T00:07:33Z",
                "html_url": "https://github.com/wala/WALA/issues/2119",
            },
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        monkeypatch.setattr(httpx, "stream", client.stream)
        snapshot = public_issue("https://github.com/wala/WALA/issues/2119")
        assert snapshot.body == body
        assert snapshot.repository == "wala/WALA"
        assert snapshot.assignees == ["liblit"]
        assert snapshot.closed_at is None
        assert len(snapshot.snapshot_sha256) == 64
        for url in (
            "http://localhost/issues/2119",
            "https://github.com/attacker/../issues/2119",
            "https://github.com/wala/WALA/issues/2119?token=example",
        ):
            with pytest.raises(HTTPException) as error:
                public_issue(url)
            assert error.value.status_code == 422
