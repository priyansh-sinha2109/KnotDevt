from app.db.identity import Role
from app.services.imports import run_import
from app.workers.celery_app import execute
from tests.support import FIXTURES, client_for, project_with


def test_failure_rolls_back_partial_worker_writes(monkeypatch) -> None:
    project, [(_, reviewer)] = project_with(Role.REVIEWER)
    with client_for(reviewer) as lead:
        base = f"/api/v1/projects/{project}"
        response = lead.post(
            base + "/imports",
            content=(FIXTURES / "issues.json").read_bytes(),
            headers={"Content-Type": "application/json"},
        )
        job = response.json()["id"]

        def fail_after_processing(db, record):
            run_import(db, record)
            db.flush()
            raise RuntimeError("Simulated failure before worker commit")

        with monkeypatch.context() as patch:
            patch.setattr("app.workers.celery_app.run_import", fail_after_processing)
            execute(job)
        assert lead.get(f"/api/v1/jobs/{job}").json()["state"] == "queued"
        assert lead.get(base + "/sources").json()["items"] == []
        execute(job)
        execute(job)
        result = lead.get(f"/api/v1/jobs/{job}").json()
        assert result["state"] == "succeeded"
        assert len(result["revisions"]) == 2
        assert all(not item["duplicate"] for item in result["revisions"])
