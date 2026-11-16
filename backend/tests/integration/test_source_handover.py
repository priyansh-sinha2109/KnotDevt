from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.evidence import AgentRun
from app.db.identity import Role
from app.db.session import engine
from app.db.sources import Job
from app.workers.celery_app import execute
from tests.support import FIXTURES, client_for, project_with


def test_source_based_handover_is_evidence_only_and_does_not_queue_ai() -> None:
    project, [(_, reviewer), (recipient_id, recipient)] = project_with(
        Role.REVIEWER, Role.RECIPIENT
    )
    prefix = f"/api/v1/projects/{project}"
    with client_for(reviewer) as lead, client_for(recipient) as incoming:
        for fixture in ("issues", "conversations"):
            response = lead.post(
                prefix + "/imports",
                content=(FIXTURES / f"{fixture}.json").read_bytes(),
                headers={"Content-Type": "application/json"},
            )
            execute(response.json()["id"])
        response = lead.post(
            prefix + "/source-handover-drafts",
            json={
                "task": "Prepare an evidence-only handover",
                "audience": [str(recipient_id)],
            },
        )
        assert response.status_code == 201, response.text
        draft = response.json()
        assert draft["mode"] == "source_based"
        assert draft["claims"]
        assert all("source_derived" in item["flags"] for item in draft["claims"])
        assert all(item["claim"]["status"] == "unverified" for item in draft["claims"])
        assert incoming.get(f"/drafts/{draft['id']}").status_code == 404
        with Session(engine()) as db:
            job = db.get(Job, draft["agent_job_id"])
            assert job is not None and job.kind == "source_handover"
            assert job.state == "succeeded"
            assert (
                db.scalars(select(AgentRun).where(AgentRun.job_id == job.id)).all()
                == []
            )
