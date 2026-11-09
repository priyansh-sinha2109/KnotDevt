from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import fake
from app.db.identity import Role
from app.db.readiness import Attempt, AttemptAdvisory
from app.db.session import engine
from app.schemas.agents import Candidate, Citation
from app.workers.celery_app import execute
from tests.support import client_for, create_demo_draft, gap_review, project_with


def correct_answers(rubric: dict) -> dict[str, int]:
    return {item["dimension"]: item["correct_choice"] for item in rubric["questions"]}


def test_perfect_score_is_blocked_and_advice_is_separate() -> None:
    project, [(_, reviewer), (recipient_id, recipient), (_, outsider)] = project_with(
        Role.REVIEWER, Role.RECIPIENT, Role.RECIPIENT
    )
    with (
        client_for(reviewer) as lead,
        client_for(recipient) as incoming,
        client_for(outsider) as other,
    ):
        draft = create_demo_draft(lead, project, recipient_id)
        rubric = draft["proposed_rubric"]
        approval = lead.post(
            f"/api/v1/drafts/{draft['id']}/approve",
            json={"expected_revision": draft["revision"], "rubric": rubric},
        )
        assert approval.status_code == 201, approval.text
        handover = approval.json()["handover"]
        rubric_url = f"/api/v1/rubrics/{handover['rubric_id']}"
        rehearsal = incoming.get(rubric_url)
        assert rehearsal.status_code == 200
        assert "correct_choice" not in rehearsal.text
        assert "explanation" not in rehearsal.text
        assert rehearsal.json()["package"] == {
            "status": "blocked_by_project_gap",
            "gates": ["critical_prerequisite"],
        }
        body = {
            "client_attempt_id": str(uuid4()),
            "answers": correct_answers(rubric),
            "explanation": "Testing and rollback ownership remain unresolved.",
        }
        assert other.post(rubric_url + "/attempts", json=body).status_code == 404
        assert lead.post(rubric_url + "/attempts", json=body).status_code == 404
        invalid = incoming.post(
            rubric_url + "/attempts", json=body | {"answers": {"action": 4}}
        )
        assert invalid.status_code == 422
        response = incoming.post(rubric_url + "/attempts", json=body)
        assert response.status_code == 201, response.text
        initial = response.json()
        assert initial["score"] == 100
        assert initial["status"] == "blocked_by_project_gap"
        assert initial["advisory"]["status"] == "queued"
        repeated = incoming.post(rubric_url + "/attempts", json=body)
        assert repeated.status_code == 200 and repeated.json()["id"] == initial["id"]
        assert (
            incoming.post(
                rubric_url + "/attempts", json=body | {"answers": {}}
            ).status_code
            == 409
        )

        attempt_id = UUID(initial["id"])
        attempt_url = f"/api/v1/attempts/{attempt_id}"
        with Session(engine()) as db:
            record = db.get(Attempt, attempt_id)
            assert record is not None
            assert record.source_revision_ids == handover["source_revision_ids"]
            job = db.scalars(
                select(AttemptAdvisory.job_id).where(
                    AttemptAdvisory.attempt_id == attempt_id
                )
            ).one()
        execute(str(job))
        result = incoming.get(attempt_url).json()
        assert result["advisory"]["status"] == "succeeded"
        assert result["score"] == 100 and result["status"] == "blocked_by_project_gap"
        assert other.get(attempt_url).status_code == 404
        assert (
            incoming.put(
                attempt_url + "/review", json={"feedback": "Unauthorized"}
            ).status_code
            == 403
        )
        revised = lead.put(
            attempt_url + "/review",
            json={"feedback": "Correctly identified the project gap."},
        ).json()
        assert revised["review_status"] == "reviewed"
        assert revised["review"]["feedback"] == "Correctly identified the project gap."
        assert revised["score"] == 100
        assert revised["status"] == "blocked_by_project_gap"


def test_resolved_package_can_pass_or_need_guided_practice(monkeypatch) -> None:
    follow_up = "Archive the release notes after deployment."
    original = fake.work

    def include_non_critical_work(bundle):
        result = original(bundle)
        source = next(item for item in bundle.evidence if item.source_id == "M-08")
        result.claims.append(
            Candidate(
                key="work_archive_notes",
                kind="work_item",
                status="open",
                statement=follow_up,
                citations=[Citation(revision_id=source.revision_id, quote=follow_up)],
            )
        )
        return result

    monkeypatch.setattr(fake, "work", include_non_critical_work)
    project, [(_, reviewer), (recipient_id, recipient)] = project_with(
        Role.REVIEWER, Role.RECIPIENT
    )
    with client_for(reviewer) as lead, client_for(recipient) as incoming:
        exact = "Payment testing is signed off. The project lead owns rollback."
        draft = create_demo_draft(
            lead,
            project,
            recipient_id,
            extra_import={
                "kind": "conversation-notes",
                "provider": "synthetic-meetings",
                "notes": [
                    {
                        "source_id": "M-08",
                        "event_type": "decision",
                        "author": "Release committee",
                        "event_at": "2026-11-03T08:00:00Z",
                        "reference": "fixture:meeting/M-08",
                        "text": f"{exact} {follow_up}",
                    }
                ],
            },
        )
        items = lead.get(
            f"/api/v1/projects/{project}/sources", params={"query": "M-08"}
        )
        source = items.json()["items"][0]
        pointer = {
            "revision_id": source["revision_id"],
            "start": 0,
            "end": len(exact),
            "quote": exact,
        }
        revision = draft["revision"]
        for item in draft["claims"]:
            claim = item["claim"]
            if claim["kind"] not in {"prerequisite", "blocker"}:
                continue
            corrected = lead.patch(
                f"/api/v1/claims/{claim['id']}",
                json={
                    "draft_id": draft["id"],
                    "expected_revision": revision,
                    "reason": "Verified against later sign-off and ownership evidence.",
                    "content": {
                        "kind": claim["kind"],
                        "status": "resolved",
                        "statement": exact,
                        "evidence": [pointer],
                    },
                },
            )
            assert corrected.status_code == 200, corrected.text
            revision = corrected.json()["draft_revision"]
        rubric = draft["proposed_rubric"]
        for question in rubric["questions"]:
            if question["dimension"] == "prerequisites":
                question.update(
                    prompt="Has payment testing been signed off?",
                    choices=["No", "Yes, per M-08"],
                    explanation="M-08 records sign-off.",
                    evidence_revision_ids=[source["revision_id"]],
                )
        draft_url = f"/api/v1/drafts/{draft['id']}"
        current = lead.get(draft_url).json()
        follow_up_claim = next(
            row["claim"]
            for row in current["claims"]
            if row["claim"]["statement"] == follow_up
        )
        review = gap_review(current)
        non_critical = next(
            item
            for item in review["claims"]
            if item["claim_revision_id"] == follow_up_claim["revision_id"]
        )
        assert non_critical["disposition"] == "non_blocking"
        non_critical["rationale"] = (
            "Release-note archiving can happen after deployment."
        )
        approval = lead.post(
            draft_url + "/approve",
            json={
                "expected_revision": revision,
                "rubric": rubric,
                "critical_gap_review": review,
            },
        )
        assert approval.status_code == 201, approval.text
        rubric_id = approval.json()["handover"]["rubric_id"]
        path = f"/api/v1/rubrics/{rubric_id}/attempts"
        low = incoming.post(path, json={"answers": {"action": 1}}).json()
        assert low["score"] == 30 and low["status"] == "needs_guided_practice"
        high = incoming.post(path, json={"answers": correct_answers(rubric)}).json()
        assert high["score"] == 100 and high["status"] == "ready_for_scoped_task"
        changed = lead.patch(
            f"/api/v1/claims/{follow_up_claim['id']}",
            json={
                "draft_id": draft["id"],
                "expected_revision": lead.get(draft_url).json()["revision"],
                "reason": "The reviewed non-critical item changed.",
                "content": {
                    "kind": "work_item",
                    "status": "open",
                    "statement": follow_up,
                    "evidence": [
                        {
                            "revision_id": source["revision_id"],
                            "start": len(exact) + 1,
                            "end": len(exact) + 1 + len(follow_up),
                            "quote": follow_up,
                        }
                    ],
                },
            },
        )
        assert changed.status_code == 200, changed.text
        published_id = approval.json()["id"]
        assert (
            incoming.get(f"/api/v1/versions/{published_id}").json()["status"] == "stale"
        )
        assert (
            lead.post(
                draft_url + "/approve",
                json={
                    "expected_revision": changed.json()["draft_revision"],
                    "rubric": rubric,
                    "critical_gap_review": review,
                },
            ).status_code
            == 409
        )
