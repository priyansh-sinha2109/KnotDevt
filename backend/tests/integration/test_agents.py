from celery.contrib.testing.worker import start_worker

from app.agents.checkpoints import checkpoints
from app.db.identity import Role
from app.workers.celery_app import DISPATCH, celery, execute
from tests.support import FIXTURES, client_for, project_with, wait_for_job


def test_parallel_agent_stages_checkpoint_and_permission() -> None:
    project, [(reviewer_id, reviewer), (recipient_id, recipient)] = project_with(
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

        body = {
            "task": "Prepare safe release of event-registration payments",
            "audience": [str(recipient_id)],
            "source_ids": ["PAY-21", "C-19", "M-07", "MISSING-01"],
        }
        assert incoming.post(prefix + "/agent-jobs", json=body).status_code == 403
        response = lead.post(prefix + "/agent-jobs", json=body)
        assert response.status_code == 202
        job_id = response.json()["id"]
        with start_worker(celery, perform_ping_check=False, pool="solo"):
            celery.send_task(DISPATCH)
            report = wait_for_job(lead, job_id)
            assert report["state"] == "succeeded", report

        with checkpoints() as saver:
            snapshot = saver.get_tuple({"configurable": {"thread_id": job_id}})
            assert snapshot is not None
        run_url = f"/api/v1/jobs/{job_id}/runs"
        response = lead.get(run_url)
        assert response.status_code == 200, response.text
        runs = {item["role"]: item for item in response.json()}
        assert len(runs) == 5
        assert all(
            run["status"] == "succeeded" and run["attempt"] == 1
            for run in runs.values()
        )
        assert runs["context_collector"]["output"]["unresolved_ids"] == ["MISSING-01"]
        assert runs["decision_analyst"]["model"] == "deterministic-fixture"
        assert "FINANCE-ONLY" not in response.text
        assert {
            claim["content"]["status"]
            for claim in runs["evidence_auditor"]["output"]["claims"]
        } == {
            "accepted",
            "proposed",
            "implemented",
            "unresolved",
        }
        assert incoming.get(run_url).status_code == 404
        execute(job_id)
        assert len(lead.get(run_url).json()) == 5

        private = lead.post(
            prefix + "/agent-jobs", json=body | {"audience": [str(reviewer_id)]}
        )
        private_job = private.json()["id"]
        execute(private_job)
        private_run = f"/api/v1/jobs/{private_job}/runs"
        assert "FINANCE-ONLY" in lead.get(private_run).text
        sources = lead.get(prefix + "/sources").json()["items"]
        source = next(item for item in sources if item["original_id"] == "FIN-12")
        assert lead.delete(f"/api/v1/sources/{source['id']}").status_code == 204
        assert lead.get(private_run).status_code == 404
