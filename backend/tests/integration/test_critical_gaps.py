from copy import deepcopy
from uuid import uuid4

from app.agents import fake
from app.db.identity import Role
from tests.integration.test_readiness import correct_answers
from tests.support import client_for, create_demo_draft, gap_review, project_with


def test_generic_work_items_cannot_make_a_perfect_score_ready(monkeypatch) -> None:
    original = fake.work

    def misclassified(bundle):
        result = original(bundle)
        for item in result.claims:
            if item.kind == "prerequisite":
                item.kind = "work_item"
                item.status = "open"
            elif item.kind == "blocker":
                item.kind = "work_item"
        return result

    monkeypatch.setattr(fake, "work", misclassified)
    project, [(_, reviewer), (recipient_id, recipient)] = project_with(
        Role.REVIEWER, Role.RECIPIENT
    )
    with client_for(reviewer) as lead, client_for(recipient) as incoming:
        draft = create_demo_draft(lead, project, recipient_id)
        draft_url = f"/api/v1/drafts/{draft['id']}"
        approve = draft_url + "/approve"
        work = [row for row in draft["claims"] if row["claim"]["kind"] == "work_item"]
        assert len(work) == 2
        assert {row["claim"]["status"] for row in work} == {"open", "unresolved"}
        assert all("critical_gap_review_required" in row["flags"] for row in work)
        assert not any(
            row["claim"]["kind"] in {"prerequisite", "blocker"}
            for row in draft["claims"]
        )
        rubric = draft["proposed_rubric"]
        body = {"expected_revision": draft["revision"], "rubric": rubric}
        legacy = lead.post(approve, json=body)
        assert legacy.status_code == 201
        legacy_version = legacy.json()

        def assess(version):
            rubric_id = version["handover"]["rubric_id"]
            result = incoming.post(
                f"/api/v1/rubrics/{rubric_id}/attempts",
                json={"answers": correct_answers(rubric)},
            )
            assert result.status_code == 201, result.text
            assert result.json()["score"] == 100
            return result.json()

        initial = assess(legacy_version)
        assert initial["status"] == "stale_or_requires_review"
        assert initial["package"]["gates"] == ["critical_gap_review_required"]

        draft = lead.get(draft_url).json()
        body["expected_revision"] = draft["revision"]
        review = gap_review(draft)
        by_revision = {row["claim"]["revision_id"]: row["claim"] for row in work}
        for item in review["claims"]:
            claim = by_revision.get(item["claim_revision_id"])
            if claim:
                item.update(
                    classification="prerequisite"
                    if claim["status"] == "open"
                    else "ownership",
                    disposition="unverified",
                    rationale="Sign-off or ownership is not established.",
                )
        body["critical_gap_review"] = review
        assert incoming.post(approve, json=body).status_code == 403

        incomplete = deepcopy(body)
        incomplete["critical_gap_review"]["claims"].pop()
        assert lead.post(approve, json=incomplete).status_code == 409
        wrong_source = deepcopy(body)
        wrong_source["critical_gap_review"]["reviewed_source_revision_ids"].pop()
        assert lead.post(approve, json=wrong_source).status_code == 409
        bogus_resolution = deepcopy(body)
        decision = next(
            i
            for i in bogus_resolution["critical_gap_review"]["claims"]
            if i["classification"] == "prerequisite"
        )
        decision["disposition"] = "resolved"
        assert lead.post(approve, json=bogus_resolution).status_code == 409

        uncertain = lead.post(approve, json=body)
        assert uncertain.status_code == 201, uncertain.text
        assert assess(uncertain.json())["status"] == "stale_or_requires_review"

        body["expected_revision"] = lead.get(draft_url).json()["revision"]
        for item in review["claims"]:
            if item["classification"] in {"prerequisite", "ownership"}:
                item["disposition"] = "blocking"
        blocked = lead.post(approve, json=body)
        assert blocked.status_code == 201, blocked.text
        result = assess(blocked.json())
        assert result["status"] == "blocked_by_project_gap"
        assert result["package"]["gates"] == ["critical_prerequisite"]
        old = incoming.get(f"/api/v1/versions/{legacy_version['id']}").json()
        assert old["status"] == "stale"
        assert (
            old["handover"]["content_hash"]
            == legacy_version["handover"]["content_hash"]
        )


def test_reviewer_can_record_missing_approval_omitted_by_model(monkeypatch) -> None:
    original = fake.work

    def omit_gaps(bundle):
        result = original(bundle)
        result.claims = []
        result.relationships = []
        return result

    monkeypatch.setattr(fake, "work", omit_gaps)
    project, [(_, reviewer), (recipient_id, recipient)] = project_with(
        Role.REVIEWER, Role.RECIPIENT
    )
    with client_for(reviewer) as lead, client_for(recipient) as incoming:
        draft = create_demo_draft(lead, project, recipient_id)
        assert all(item["claim"]["kind"] == "decision" for item in draft["claims"])
        source = lead.get(
            f"/api/v1/projects/{project}/sources", params={"query": "M-07"}
        )
        source_id = source.json()["items"][0]["revision_id"]
        rubric = draft["proposed_rubric"]
        body = {
            "expected_revision": draft["revision"],
            "rubric": rubric,
            "critical_gap_review": gap_review(draft),
        }
        review = body["critical_gap_review"]
        review["additional_gaps"] = [
            {
                "classification": "approval",
                "disposition": "blocking",
                "source_revision_id": str(uuid4()),
                "rationale": "Conditional approval requires missing testing sign-off.",
            }
        ]
        approve = f"/api/v1/drafts/{draft['id']}/approve"
        assert lead.post(approve, json=body).status_code == 422
        review["additional_gaps"][0]["source_revision_id"] = source_id
        approved = lead.post(approve, json=body)
        assert approved.status_code == 201, approved.text
        rubric_id = approved.json()["handover"]["rubric_id"]
        result = incoming.post(
            f"/api/v1/rubrics/{rubric_id}/attempts",
            json={"answers": correct_answers(rubric)},
        )
        assert result.status_code == 201
        assert result.json()["score"] == 100
        assert result.json()["status"] == "blocked_by_project_gap"
