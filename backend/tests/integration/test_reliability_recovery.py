from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.handover import Version
from app.db.identity import Role
from app.db.session import engine
from app.db.sources import Job
from app.services.review_resume import resume_review
from app.workers.celery_app import execute
from tests.support import client_for, create_demo_draft, project_with


def test_checkpoint_outage_then_partial_success_and_duplicate_delivery(monkeypatch):
    project, [(_, reviewer), (recipient_id, _)] = project_with(
        Role.REVIEWER, Role.RECIPIENT
    )
    with client_for(reviewer) as lead:
        draft = create_demo_draft(lead, project, recipient_id)
        response = lead.post(
            f"/api/v1/drafts/{draft['id']}/approve",
            json={
                "expected_revision": draft["revision"],
                "rubric": draft["proposed_rubric"],
            },
        )
        assert response.status_code == 201
        version_id = UUID(response.json()["id"])
        with Session(engine()) as db:
            job_id = db.get(Version, version_id).resume_job_id

        def outage(db, job):
            raise ConnectionError("synthetic checkpoint outage")

        with monkeypatch.context() as patch:
            patch.setattr("app.workers.celery_app.resume_review", outage)
            for _ in range(4):
                execute(str(job_id))
        with Session(engine()) as db:
            job = db.get(Job, job_id)
            assert job.state == "queued"
            assert job.error_code == "checkpoint_retry_scheduled"

        def crash_after_checkpoint(db, job):
            resume_review(db, job)
            raise ConnectionError("synthetic loss after checkpoint commit")

        with monkeypatch.context() as patch:
            patch.setattr(
                "app.workers.celery_app.resume_review", crash_after_checkpoint
            )
            execute(str(job_id))
        execute(str(job_id))
        execute(str(job_id))
        with Session(engine()) as db:
            job = db.get(Job, job_id)
            assert job.state == "succeeded"
            assert job.error_code is None
            assert (
                len(
                    db.scalars(
                        select(Version).where(Version.draft_id == UUID(draft["id"]))
                    ).all()
                )
                == 1
            )
        assert lead.get(f"/api/v1/versions/{version_id}").json() == response.json()


def test_invitation_rollback_then_concurrent_redemption(monkeypatch):
    project, [(_, owner)] = project_with(Role.ADMIN)
    _, [(_, incoming)] = project_with(Role.RECIPIENT)
    with (
        client_for(owner) as admin,
        client_for(incoming) as first,
        client_for(incoming) as second,
    ):
        body = admin.post(
            f"/api/v1/projects/{project}/invitations", json={"email": incoming}
        ).json()
        path = "/api/v1/invitations/redeem"
        with monkeypatch.context() as patch:

            def fail_commit(self):
                raise RuntimeError("synthetic database failure")

            patch.setattr(Session, "commit", fail_commit)
            assert first.post(path, json=body).status_code == 500
        assert first.get(f"/api/v1/projects/{project}").status_code == 404
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [
                pool.submit(client.post, path, json=body) for client in (first, second)
            ]
            assert sorted(result.result().status_code for result in results) == [
                200,
                404,
            ]
        assert first.get(f"/api/v1/projects/{project}").status_code == 200


def test_failed_import_explicit_retry_preserves_identity(monkeypatch):
    from tests.support import FIXTURES

    project, [(_, reviewer)] = project_with(Role.REVIEWER)
    with client_for(reviewer) as lead:
        path = f"/api/v1/projects/{project}/imports"
        content = (FIXTURES / "issues.json").read_bytes()
        headers = {"Content-Type": "application/json", "Idempotency-Key": "recovery"}
        original = lead.post(path, content=content, headers=headers).json()

        def outage(db, job):
            raise ConnectionError("synthetic import connection failure")

        with monkeypatch.context() as patch:
            patch.setattr("app.workers.celery_app.run_import", outage)
            for _ in range(3):
                execute(original["id"])
        replay = lead.post(path, content=content, headers=headers).json()
        assert replay["id"] == original["id"]
        assert replay["state"] == "failed"
        retry = f"/api/v1/jobs/{original['id']}/retry"
        assert lead.post(retry).json()["state"] == "queued"
        assert lead.post(retry).json()["id"] == original["id"]
        execute(original["id"])
        execute(original["id"])
        assert len(lead.get(f"/api/v1/projects/{project}/sources").json()["items"]) == 2


def test_work_mapper_missing_status_recovers_without_repeating_success(monkeypatch):
    import json

    from app.agents import fake
    from app.agents.provider import validate_output
    from app.schemas.agents import WorkOutput

    original = fake.work
    calls = 0

    def interrupted(bundle):
        nonlocal calls
        calls += 1
        value = original(bundle)
        if calls == 1:
            raw = value.model_dump(mode="json")
            del raw["claims"][0]["status"]
            return validate_output(json.dumps(raw), WorkOutput)
        return value

    monkeypatch.setattr(fake, "work", interrupted)
    # This recovery test explicitly exercises a second bounded attempt; the
    # local Groq runtime defaults to one attempt to protect free-tier quota.
    from app.core.config import settings
    monkeypatch.setattr(settings(), "agent_attempts", 2)
    project, [(_, reviewer), (recipient_id, _)] = project_with(
        Role.REVIEWER, Role.RECIPIENT
    )
    with client_for(reviewer) as lead:
        draft = create_demo_draft(lead, project, recipient_id)
        runs = lead.get(f"/api/v1/jobs/{draft['agent_job_id']}/runs").json()
        work = [run for run in runs if run["role"] == "work_mapper"]
        assert [run["status"] for run in work] == ["failed", "succeeded"]
        assert work[0]["error_code"] == "invalid_output"
        assert len([run for run in runs if run["role"] == "decision_analyst"]) == 1
        assert calls == 2


def test_high_impact_correction_requires_supporting_evidence():
    project, [(_, reviewer), (recipient_id, _)] = project_with(
        Role.REVIEWER, Role.RECIPIENT
    )
    with client_for(reviewer) as lead:
        draft = create_demo_draft(lead, project, recipient_id)
        claim = draft["claims"][0]["claim"]
        source = draft["source_snapshot"][0]
        quote = source["excerpt"][:30]
        body = {
            "draft_id": draft["id"],
            "expected_revision": draft["revision"],
            "reason": "Synthetic reviewer correction with explicit evidence.",
            "content": {
                "kind": claim["kind"],
                "status": "confirmed",
                "statement": claim["statement"],
                "evidence": [
                    {
                        "revision_id": source["revision_id"],
                        "quote": quote,
                        "start": 0,
                        "end": len(quote),
                        "relation": "contradicts",
                    }
                ],
            },
        }
        path = f"/api/v1/claims/{claim['id']}"
        for status in ("confirmed", "implemented", "resolved"):
            body["content"]["status"] = status
            assert lead.patch(path, json=body).status_code == 422
        body["content"]["evidence"][0]["relation"] = "supports"
        assert lead.patch(path, json=body).status_code == 200
