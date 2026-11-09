from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.agents.checkpoints import checkpoints
from app.db.handover import Version
from app.db.identity import Role
from app.db.session import engine
from app.db.sources import Job
from app.workers.celery_app import execute
from tests.support import client_for, create_demo_draft, project_with


def test_reviewer_edits_approves_and_withdraws_exact_version() -> None:
    project, [(_, reviewer), (recipient_id, recipient), (_, outsider)] = project_with(
        Role.REVIEWER, Role.RECIPIENT, Role.RECIPIENT
    )
    with (
        client_for(reviewer) as lead,
        client_for(recipient) as incoming,
        client_for(outsider) as other,
    ):
        draft = create_demo_draft(lead, project, recipient_id)
        draft_url = f"/api/v1/drafts/{draft['id']}"
        assert lead.get(draft_url).json() == draft
        assert incoming.get(draft_url).status_code == 403
        rollback = next(
            item["claim"]
            for item in draft["claims"]
            if item["claim"]["kind"] == "blocker"
        )
        claim_path = f"/api/v1/claims/{rollback['id']}"
        correction = {
            "draft_id": draft["id"],
            "expected_revision": draft["revision"],
            "content": {
                "kind": "blocker",
                "status": "unresolved",
                "statement": "Rollback owner is unconfirmed. Escalate to lead.",
            },
            "reason": "Clarify the escalation while preserving the unresolved gap.",
        }
        assert incoming.patch(claim_path, json=correction).status_code == 403
        updated = lead.patch(claim_path, json=correction)
        assert updated.status_code == 200, updated.text
        assert lead.patch(claim_path, json=correction).status_code == 409

        approve_path = draft_url + "/approve"
        body = {
            "expected_revision": updated.json()["draft_revision"],
            "rubric": draft["proposed_rubric"],
        }
        assert (
            lead.post(approve_path, json=body | {"expected_revision": 1}).status_code
            == 409
        )
        assert incoming.post(approve_path, json=body).status_code == 403
        approved = lead.post(approve_path, json=body)
        assert approved.status_code == 201, approved.text
        result = approved.json()
        version_id = UUID(result["id"])
        assert result["status"] == "approved"
        version_url = f"/api/v1/versions/{version_id}"
        assert incoming.get(version_url).json() == result
        assert other.get(version_url).status_code == 404
        assert "correct_choice" not in incoming.get(version_url).text

        with Session(engine()) as db:
            resume_id = db.scalars(
                select(Version.resume_job_id).where(Version.id == version_id)
            ).one()
        execute(str(resume_id))
        with Session(engine()) as db:
            assert db.get(Job, resume_id).state == "succeeded"
        with checkpoints() as saver:
            saved = saver.get_tuple(
                {"configurable": {"thread_id": draft["agent_job_id"]}}
            )
            assert saved is not None
            assert saved.checkpoint["channel_values"]["approved"] is True

        with pytest.raises(DBAPIError, match="immutable record"):
            with engine().begin() as conn:
                conn.execute(
                    update(Version)
                    .where(Version.id == version_id)
                    .values(task="Changed")
                )

        correction["expected_revision"] = lead.get(draft_url).json()["revision"]
        correction["content"]["statement"] = "A later draft edit."
        assert lead.patch(claim_path, json=correction).status_code == 200
        assert incoming.get(version_url).json() == result
        assert incoming.post(version_url + "/withdraw").status_code == 403
        assert lead.post(version_url + "/withdraw").status_code == 204
        assert lead.post(version_url + "/withdraw").status_code == 204
        assert incoming.get(version_url).json() == {
            "id": str(version_id),
            "status": "withdrawn",
            "handover": None,
        }


def test_approval_is_atomic_under_concurrency() -> None:
    project, [(_, reviewer), (recipient_id, _)] = project_with(
        Role.REVIEWER, Role.RECIPIENT
    )
    with client_for(reviewer) as first, client_for(reviewer) as second:
        draft = create_demo_draft(first, project, recipient_id)
        body = {
            "expected_revision": draft["revision"],
            "rubric": draft["proposed_rubric"],
        }
        path = f"/api/v1/drafts/{draft['id']}/approve"
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = [
                pool.submit(client.post, path, json=body) for client in (first, second)
            ]
            assert sorted(response.result().status_code for response in responses) == [
                201,
                409,
            ]
        with Session(engine()) as db:
            versions = db.scalars(
                select(Version).where(Version.draft_id == UUID(draft["id"]))
            ).all()
            assert len(versions) == 1
