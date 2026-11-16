from urllib.parse import parse_qs, urlparse

from app.integrations.providers import authorize_url


def test_github_authorization_asks_person_to_choose_account():
    url = urlparse(authorize_url("github", "single-use-test-state"))
    query = parse_qs(url.query)
    assert url.netloc == "github.com"
    assert query["prompt"] == ["select_account"]
    assert query["state"] == ["single-use-test-state"]
    assert "login" not in query
