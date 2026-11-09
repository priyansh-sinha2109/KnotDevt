from uuid import uuid4

from app.db.identity import Role
from tests.support import client_for, create_demo_draft, project_with


def test_context_trace_distinguishes_proposal_approval_and_implementation() -> None:
    project, [(_, reviewer), (recipient_id, recipient), (_, outsider)] = project_with(
        Role.REVIEWER, Role.RECIPIENT, Role.RECIPIENT
    )
    with (
        client_for(reviewer) as lead,
        client_for(recipient) as incoming,
        client_for(outsider) as other,
    ):
        draft = create_demo_draft(lead, project, recipient_id)
        monday = next(
            row["claim"]["id"]
            for row in draft["claims"]
            if row["claim"]["status"] == "accepted"
        )
        trace_url = f"/api/v1/claims/{monday}/trace"
        assert lead.get(trace_url).json()["status"] == "current"
        assert incoming.get(trace_url).status_code == 404
        published = lead.post(
            f"/api/v1/drafts/{draft['id']}/approve",
            json={
                "expected_revision": draft["revision"],
                "rubric": draft["proposed_rubric"],
            },
        ).json()
        scope = {"version_id": published["id"]}
        response = incoming.get(trace_url, params=scope)
        assert response.status_code == 200
        trace = response.json()
        assert trace["selected"]["claim"]["status"] == "accepted"
        assert trace["selected"]["evidence"][0]["original_id"] == "M-07"
        timeline = {
            item["evidence"][0]["original_id"]: item["claim"]["status"]
            for item in trace["timeline"]
            if item["claim"]["kind"] == "decision"
        }
        assert timeline == {
            "PAY-21": "proposed",
            "C-19": "implemented",
            "M-07": "accepted",
        }
        assert {"requires", "supersedes"} <= {
            edge["relation"] for edge in trace["relationships"]
        }
        assert "rollback ownership" in response.text.lower()
        assert "reason for choosing Monday is missing" in response.text
        assert "FINANCE-ONLY" not in response.text
        assert other.get(trace_url, params=scope).status_code == 404
        assert (
            incoming.get(f"/api/v1/claims/{uuid4()}/trace", params=scope).status_code
            == 404
        )

        source = trace["selected"]["evidence"][0]["source_id"]
        assert (
            lead.put(
                f"/api/v1/sources/{source}/policy", json={"policy": "restricted"}
            ).status_code
            == 204
        )
        redacted = incoming.get(trace_url, params=scope).json()
        assert redacted["status"] == "unavailable"
        assert redacted["selected"] is None and redacted["timeline"] == []
        assert redacted["outline"] == [] and redacted["unresolved"] == []
