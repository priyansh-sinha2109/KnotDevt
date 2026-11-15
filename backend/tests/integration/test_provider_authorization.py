from unittest.mock import Mock
from uuid import UUID

from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.identity import Role
from app.db.session import engine
from app.db.sources import Job
from app.workers.celery_app import celery, dispatch, execute
from tests.support import client_for, create_demo_draft, project_with


def test_new_openai_job_is_routed_but_not_executed_until_authorized(monkeypatch):
    project, [(_, reviewer), (recipient_id, _)] = project_with(
        Role.REVIEWER, Role.RECIPIENT
    )
    with client_for(reviewer) as lead:
        create_demo_draft(lead, project, recipient_id)
        monkeypatch.setattr(settings(), "llm_provider", "openai")
        monkeypatch.setattr(settings(), "openai_api_key", SecretStr("synthetic-only"))
        forbidden = Mock(side_effect=AssertionError("No live calls permitted"))
        monkeypatch.setattr("app.agents.provider.generate", forbidden)
        response = lead.post(
            f"/api/v1/projects/{project}/agent-jobs",
            json={
                "task": "Authorization gate regression",
                "audience": [str(recipient_id)],
            },
        )
        assert response.status_code == 202
        job = response.json()["id"]
        assert response.json()["phase"] == "awaiting_provider_authorization"
        execute(job)
        result = lead.get(f"/api/v1/jobs/{job}").json()
        assert result["state"] == "queued" and result["attempt_count"] == 0
        assert lead.get(f"/api/v1/jobs/{job}/runs").json() == []
        send = Mock()
        monkeypatch.setattr(celery, "send_task", send)
        dispatch([job])
        send.assert_not_called()
        forbidden.assert_not_called()


def test_unassigned_historical_job_is_not_dispatched_or_executed(monkeypatch):
    project, [(_, reviewer), (recipient_id, _)] = project_with(
        Role.REVIEWER, Role.RECIPIENT
    )
    with client_for(reviewer) as lead:
        draft = create_demo_draft(lead, project, recipient_id)
        job = UUID(draft["agent_job_id"])
        with Session(engine()) as db, db.begin():
            row = db.get(Job, job)
            row.queue = None
            row.state = "queued"
            previous_attempts = row.attempts
        send = Mock()
        monkeypatch.setattr(celery, "send_task", send)
        dispatch([str(job)])
        execute(str(job))
        send.assert_not_called()
        with Session(engine()) as db:
            row = db.get(Job, job)
            assert row.state == "queued" and row.attempts == previous_attempts
