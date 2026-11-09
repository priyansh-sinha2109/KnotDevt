from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.identity import Role
from app.db.readiness import Attempt
from app.db.session import engine
from tests.integration.test_readiness import correct_answers
from tests.support import client_for, create_demo_draft, project_with


def test_receipt_is_independent_concurrent_and_assigned() -> None:
    project, [(_, reviewer), (recipient_id, recipient), (_, outsider)] = project_with(
        Role.REVIEWER, Role.RECIPIENT, Role.RECIPIENT
    )
    with (
        client_for(reviewer) as lead,
        client_for(recipient) as incoming,
        client_for(recipient) as retry,
        client_for(outsider) as other,
    ):
        draft = create_demo_draft(lead, project, recipient_id)
        approval = lead.post(
            f"/api/v1/drafts/{draft['id']}/approve",
            json={
                "expected_revision": draft["revision"],
                "rubric": draft["proposed_rubric"],
            },
        )
        version = approval.json()["id"]
        path = f"/api/v1/versions/{version}/receipt"
        assert incoming.get(path).status_code == 404
        assert other.post(path).status_code == 404
        assert lead.post(path).status_code == 404
        with ThreadPoolExecutor(max_workers=2) as pool:
            replies = list(
                pool.map(lambda client: client.post(path), (incoming, retry))
            )
        assert sorted(item.status_code for item in replies) == [200, 201]
        assert replies[0].json() == replies[1].json() == incoming.get(path).json()
        assert set(replies[0].json()) == {
            "version_id",
            "recipient_id",
            "acknowledged_at",
        }
        with Session(engine()) as db:
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(Attempt)
                    .where(Attempt.version_id == UUID(version))
                )
                == 0
            )


def test_revocation_redacts_current_historical_and_feedback() -> None:
    project, [(_, reviewer), (recipient_id, recipient), (_, admin)] = project_with(
        Role.REVIEWER, Role.RECIPIENT, Role.ADMIN
    )
    with (
        client_for(reviewer) as lead,
        client_for(recipient) as incoming,
        client_for(admin) as mgr,
    ):
        draft = create_demo_draft(lead, project, recipient_id)
        approval = {
            "expected_revision": draft["revision"],
            "rubric": draft["proposed_rubric"],
        }
        draft_url = f"/api/v1/drafts/{draft['id']}"
        first = lead.post(draft_url + "/approve", json=approval).json()
        rubric_url = f"/api/v1/rubrics/{first['handover']['rubric_id']}"
        attempt = incoming.post(
            rubric_url + "/attempts",
            json={
                "answers": correct_answers(draft["proposed_rubric"]),
                "explanation": "Synthetic protected feedback marker EXPLANATION-01.",
            },
        ).json()
        attempt_url = f"/api/v1/attempts/{attempt['id']}"
        assert attempt["score"] == 100
        approval["rubric"]["threshold"] = 85
        approval["expected_revision"] = lead.get(draft_url).json()["revision"]
        second = lead.post(draft_url + "/approve", json=approval)
        assert second.status_code == 201
        first_url = f"/api/v1/versions/{first['id']}"
        second_url = f"/api/v1/versions/{second.json()['id']}"
        assert incoming.get(first_url).json()["status"] == "stale"
        assert incoming.get(attempt_url).json()["status"] == "stale_or_requires_review"
        assert incoming.post(first_url + "/receipt").status_code == 409
        assert incoming.post(second_url + "/receipt").status_code == 201

        source_path = f"/api/v1/projects/{project}/sources"
        source = lead.get(source_path, params={"query": "M-07"}).json()["items"][0]
        acl = f"/api/v1/sources/{source['id']}/policy"
        assert lead.put(acl, json={"policy": "project"}).status_code == 204
        assert incoming.get(second_url).json()["status"] == "approved"
        assert lead.put(acl, json={"policy": "restricted"}).status_code == 204
        for url in (first_url, second_url):
            withheld = incoming.get(url).json()
            assert withheld["status"] == "unavailable" and withheld["handover"] is None
        assert incoming.get(second_url + "/receipt").status_code == 409
        assert incoming.get(source_path, params={"query": "M-07"}).json()["items"] == []
        assert incoming.get(rubric_url).json()["questions"] == []
        report = incoming.get(attempt_url).json()
        assert report["status"] == "access_review_required"
        assert report["score"] is None and report["feedback"] == []
        assert report["advisory"] is None and report["explanation"] is None
        assert lead.get(attempt_url).json()["status"] == "access_review_required"
        assert mgr.get(attempt_url).json()["score"] is None
        assert (
            mgr.delete(f"/api/v1/projects/{project}/members/{recipient_id}").status_code
            == 204
        )
        assert incoming.get(second_url).status_code == 404
