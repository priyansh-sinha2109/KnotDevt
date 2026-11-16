from types import SimpleNamespace
from unittest.mock import Mock

from app.db.identity import Role
from tests.support import client_for, project_with


def test_public_research_requires_project_editor_and_operator_enable(monkeypatch):
    project, [(_, reviewer), (_, recipient)] = project_with(
        Role.REVIEWER, Role.RECIPIENT
    )
    adapter = Mock(return_value={"verified": False, "results": []})
    monkeypatch.setattr("app.api.agents.research", adapter)
    monkeypatch.setattr(
        "app.api.agents.settings",
        lambda: SimpleNamespace(public_research_enabled=False),
    )
    path = f"/api/v1/projects/{project}/public-research"
    body = {"query": "public release history", "domains": ["github.com"]}
    with client_for(reviewer) as lead, client_for(recipient) as incoming:
        assert incoming.post(path, json=body).status_code == 403
        assert lead.post(path, json=body).status_code == 503
        adapter.assert_not_called()
        monkeypatch.setattr(
            "app.api.agents.settings",
            lambda: SimpleNamespace(public_research_enabled=True),
        )
        response = lead.post(path, json=body)
        assert response.status_code == 200 and response.json()["verified"] is False
        adapter.assert_called_once_with(body["query"], body["domains"], permitted=True)
