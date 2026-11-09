from app.db.identity import Role
from tests.support import client_for, create_demo_draft, project_with


def test_workspace_review_queue_and_recipient_discovery() -> None:
    project, [(_, reviewer), (recipient_id, recipient), (_, unrelated)] = project_with(
        Role.REVIEWER, Role.RECIPIENT, Role.RECIPIENT
    )
    with (
        client_for(reviewer) as lead,
        client_for(recipient) as incoming,
        client_for(unrelated) as other,
    ):
        base = f"/api/v1/projects/{project}"
        workspace = incoming.get("/api/v1/workspaces").json()["items"][0]
        workspace_url = f"/api/v1/workspaces/{workspace['id']}/projects"
        assert incoming.get(workspace_url).json()["items"][0]["id"] == str(project)
        assert workspace["role"] == "recipient"
        draft = create_demo_draft(lead, project, recipient_id)
        review_queue = base + "/drafts"
        assert incoming.get(review_queue).status_code == 403
        assert lead.get(review_queue).json()["items"][0]["id"] == draft["id"]
        versions = base + "/versions"
        assert incoming.get(versions).json()["items"] == []
        approved = lead.post(
            f"/api/v1/drafts/{draft['id']}/approve",
            json={
                "expected_revision": draft["revision"],
                "rubric": draft["proposed_rubric"],
            },
        )
        assert approved.status_code == 201
        assert lead.get(review_queue).json()["items"] == []
        assert incoming.get(versions).json()["items"][0]["id"] == approved.json()["id"]
        assert other.get(versions).json()["items"] == []
        source = lead.get(base + "/sources", params={"query": "M-07"}).json()["items"][
            0
        ]
        assert (
            lead.put(
                f"/api/v1/sources/{source['id']}/policy",
                json={"policy": "restricted"},
            ).status_code
            == 204
        )
        assert incoming.get(versions).json() == {"items": [], "next_offset": None}
