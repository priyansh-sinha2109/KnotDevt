from app.workers.celery_app import celery


def test_connector_tasks_registered_and_isolated():
    for name in ("knotdevt.connectors.sync", "knotdevt.connectors.dispatch"):
        assert name in celery.tasks
        route = celery.amqp.router.route({}, name)
        assert route["queue"].name == "knotdevt-connectors"
    # The test fixture changes the default queue after module import.
    declared = {q.name for q in celery.conf.task_queues}
    assert "knotdevt-connectors" in declared
    assert "celery" not in declared
    assert len(declared) == 2
    recovery = celery.conf.beat_schedule["recover-connector-syncs"]
    assert recovery["options"]["queue"] == "knotdevt-connectors"
