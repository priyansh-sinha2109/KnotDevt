import json

from celery.contrib.testing.worker import start_worker
from sqlalchemy.orm import Session

from app.db.identity import Role
from app.db.session import engine
from app.db.sources import ImportPayload, Job
from app.services.access import require_project
from app.workers.celery_app import DISPATCH, EXECUTE, celery, dispatch, execute
from tests.support import FIXTURES, client_for, project_with, wait_for_job


def test_two_adapters_actual_worker_and_source_permission() -> None:
    project, accounts = project_with(Role.REVIEWER, Role.ADMIN, Role.RECIPIENT)
    (reviewer_id, reviewer), (_, admin), (recipient_id, recipient) = accounts
    path = f"/api/v1/projects/{project}/imports"
    issues = (FIXTURES / "issues.json").read_bytes()
    notes = (FIXTURES / "conversations.json").read_bytes()

    with (
        client_for(reviewer) as lead,
        client_for(admin) as administrator,
        client_for(recipient) as incoming,
    ):
        assert incoming.post(path, json={}).status_code == 403
        assert lead.post(path, content=b"not JSON").status_code == 415
        assert lead.post(path, json={"kind": "unknown"}).status_code == 422
        json_headers = {"Content-Type": "application/json"}
        oversized = lead.post(
            path, content=b"x" * (1024 * 1024 + 1), headers=json_headers
        )
        assert oversized.status_code == 413
        first = lead.post(
            path, content=issues, headers=json_headers | {"Idempotency-Key": "a"}
        )
        second = lead.post(path, content=notes, headers=json_headers)
        assert first.status_code == second.status_code == 202
        first_id, second_id = first.json()["id"], second.json()["id"]
        duplicate_request = lead.post(
            path, content=issues, headers=json_headers | {"Idempotency-Key": "a"}
        )
        assert duplicate_request.json()["id"] == first_id
        assert (
            lead.post(
                path, content=notes, headers=json_headers | {"Idempotency-Key": "a"}
            ).status_code
            == 409
        )

        with start_worker(celery, perform_ping_check=False, pool="solo"):
            celery.send_task(DISPATCH)
            assert wait_for_job(lead, first_id)["state"] == "succeeded"
            assert wait_for_job(lead, second_id)["state"] == "succeeded"
            celery.send_task(EXECUTE, args=[first_id])

            duplicate = lead.post(path, content=issues, headers=json_headers).json()[
                "id"
            ]
            dispatch()
            report = wait_for_job(lead, duplicate)
            assert len(report["revisions"]) == 2
            assert all(item["duplicate"] for item in report["revisions"])

            updated = json.loads(issues)
            updated["events"][0]["text"] += " More context was supplied."
            revised = lead.post(path, json=updated).json()["id"]
            dispatch()
            report = wait_for_job(lead, revised)
            assert sum(not item["duplicate"] for item in report["revisions"]) == 1

        listing = f"/api/v1/projects/{project}/sources"
        all_sources = lead.get(listing).json()["items"]
        restricted = next(
            source for source in all_sources if source["original_id"] == "FIN-12"
        )
        restricted_path = f"/api/v1/sources/{restricted['id']}"
        assert administrator.get(restricted_path).status_code == 404
        assert incoming.get(restricted_path).status_code == 404
        assert "FINANCE-ONLY" not in incoming.get(listing).text
        assert incoming.get(f"/api/v1/jobs/{second_id}").status_code == 404
        policy_path = restricted_path + "/policy"
        assert (
            lead.put(
                policy_path,
                json={
                    "policy": "restricted",
                    "allowed_users": [str(recipient_id)],
                },
            ).status_code
            == 204
        )
        assert incoming.get(restricted_path).status_code == 200
        assert lead.put(policy_path, json={"policy": "restricted"}).status_code == 204
        assert incoming.get(restricted_path).status_code == 404
        assert lead.delete(restricted_path).status_code == 204
        assert lead.get(restricted_path).status_code == 404
        assert len(lead.get(f"/api/v1/jobs/{second_id}").json()["revisions"]) == 1

        with Session(engine()) as db:
            from uuid import UUID

            require_project(db, project, reviewer_id)
            assert db.get(ImportPayload, UUID(first_id)).original == issues
            assert db.get(Job, UUID(first_id)).attempts == 1


def test_broker_failure_preserves_accepted_import(monkeypatch) -> None:
    project, [(_, reviewer)] = project_with(Role.REVIEWER)
    with client_for(reviewer) as lead:
        payload = json.loads((FIXTURES / "issues.json").read_bytes())
        job = lead.post(f"/api/v1/projects/{project}/imports", json=payload).json()[
            "id"
        ]

        def failed_send(*args, **kwargs):
            raise ConnectionError("synthetic broker outage")

        with monkeypatch.context() as patch:
            patch.setattr(celery, "send_task", failed_send)
            try:
                dispatch()
            except ConnectionError:
                pass
            else:
                raise AssertionError("Expected simulated outage")
        assert lead.get(f"/api/v1/jobs/{job}").json()["state"] == "queued"
        with start_worker(celery, perform_ping_check=False, pool="solo"):
            dispatch()
            assert wait_for_job(lead, job)["state"] == "succeeded"
        execute(job)
        assert len(lead.get(f"/api/v1/jobs/{job}").json()["revisions"]) == 2
