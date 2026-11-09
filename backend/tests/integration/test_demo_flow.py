from celery.contrib.testing.worker import start_worker

from app.db.identity import Role
from app.workers.celery_app import celery, dispatch
from scripts.verify_local import run_workflow
from tests.support import client_for, project_with


def test_complete_judge_flow_with_real_redis_and_celery() -> None:
    project, [(_, lead), (recipient_id, incoming)] = project_with(
        Role.REVIEWER, Role.RECIPIENT
    )
    _, [(_, restricted)] = project_with(Role.RECIPIENT)
    with (
        client_for(lead) as reviewer,
        client_for(incoming) as recipient,
        client_for(restricted) as outsider,
        start_worker(celery, perform_ping_check=False, pool="solo"),
    ):
        result = run_workflow(
            reviewer, recipient, outsider, project, recipient_id, tick=dispatch
        )
        assert result["version_id"]
