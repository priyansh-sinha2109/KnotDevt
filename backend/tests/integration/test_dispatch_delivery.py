from uuid import UUID, uuid4

from celery.contrib.testing.worker import start_worker
from sqlalchemy.orm import Session

from app.db.identity import Role
from app.db.session import engine
from app.db.sources import Job
from app.workers.celery_app import EXECUTE, celery, dispatch
from tests.support import (
    FIXTURES,
    client_for,
    create_demo_draft,
    project_with,
    wait_for_job,
)


def isolated_delivery(monkeypatch):
    from app.core.config import settings

    assert settings().llm_provider == "fake"
    monkeypatch.setattr(
        "app.agents.provider.generate",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("Live provider forbidden in dispatch regression")
        ),
    )
    queue = "dispatch-regression-" + uuid4().hex
    original = celery.send_task

    def send(name, args=None, **kwargs):
        kwargs["queue"] = queue
        return original(name, args=args, **kwargs)

    monkeypatch.setattr(celery, "send_task", send)
    return queue


def test_committed_acceptance_delivers_and_duplicate_agent_messages_are_noops(
    monkeypatch,
):
    queue = isolated_delivery(monkeypatch)
    project, [(_, reviewer), (recipient_id, _)] = project_with(
        Role.REVIEWER, Role.RECIPIENT
    )
    with client_for(reviewer) as lead:
        # Build deterministic evidence before starting the dedicated worker.
        draft = create_demo_draft(lead, project, recipient_id)
        with start_worker(
            celery, perform_ping_check=False, pool="solo", queues=[queue]
        ):
            response = lead.post(
                f"/api/v1/projects/{project}/agent-jobs",
                json={
                    "task": "Verify accepted job delivery",
                    "audience": [str(recipient_id)],
                },
            )
            assert response.status_code == 202
            job = response.json()["id"]
            report = wait_for_job(lead, job)
            assert report["phase"] == "awaiting_human_review"
            runs = lead.get(f"/api/v1/jobs/{job}/runs").json()
            assert len(runs) == 5 and all(r["status"] == "succeeded" for r in runs)
            celery.send_task(EXECUTE, args=[job])
            # A synchronous duplicate additionally verifies the transaction guard.
            from app.workers.celery_app import execute

            execute(job)
            assert lead.get(f"/api/v1/jobs/{job}/runs").json() == runs
            assert lead.get(f"/api/v1/jobs/{job}").json()["attempt_count"] == 1
        assert draft["id"]


def test_broker_failure_after_commit_is_recovered_by_scoped_dispatch(monkeypatch):
    queue = isolated_delivery(monkeypatch)
    send = celery.send_task
    observed = []

    def unavailable(name, args=None, **kwargs):
        with Session(engine()) as db:
            row = db.get(Job, UUID(args[0]))
            assert row is not None and row.state == "queued"
        observed.append(args[0])
        raise ConnectionError("synthetic broker outage")

    project, [(_, reviewer)] = project_with(Role.REVIEWER)
    with client_for(reviewer) as lead:
        monkeypatch.setattr(celery, "send_task", unavailable)
        response = lead.post(
            f"/api/v1/projects/{project}/imports",
            content=(FIXTURES / "issues.json").read_bytes(),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 202
        job = response.json()["id"]
        assert observed == [job]
        monkeypatch.setattr(celery, "send_task", send)
        with start_worker(
            celery, perform_ping_check=False, pool="solo", queues=[queue]
        ):
            dispatch([job])
            dispatch([job])
            assert wait_for_job(lead, job)["state"] == "succeeded"
        report = lead.get(f"/api/v1/jobs/{job}").json()
        assert report["attempt_count"] == 1
        assert len(report["revisions"]) == 2


def test_lost_message_is_redispatched_when_schedule_is_due(monkeypatch):
    from datetime import UTC, datetime, timedelta

    queue = isolated_delivery(monkeypatch)
    send = celery.send_task
    monkeypatch.setattr(celery, "send_task", lambda *args, **kwargs: None)
    project, [(_, reviewer)] = project_with(Role.REVIEWER)
    with client_for(reviewer) as lead:
        response = lead.post(
            f"/api/v1/projects/{project}/imports",
            content=(FIXTURES / "issues.json").read_bytes(),
            headers={"Content-Type": "application/json"},
        )
        job = response.json()["id"]
        dispatch([job])  # Simulate broker accepting then losing the message.
        with Session(engine()) as db, db.begin():
            row = db.get(Job, UUID(job))
            assert row.state == "queued" and row.attempts == 0
            row.dispatch_after = datetime.now(UTC) - timedelta(seconds=1)
        monkeypatch.setattr(celery, "send_task", send)
        with start_worker(
            celery, perform_ping_check=False, pool="solo", queues=[queue]
        ):
            dispatch([job])
            dispatch([job])
            assert wait_for_job(lead, job)["state"] == "succeeded"
        assert lead.get(f"/api/v1/jobs/{job}").json()["attempt_count"] == 1
