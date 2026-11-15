"""Import-only local worker; cannot execute or recover an AI workflow job."""

import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from celery import Celery
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import engine
from app.db.sources import Job

config = settings()
config.job_queue = "knotdevt-imports"
from app.workers.celery_app import execute  # noqa: E402

celery = Celery("knotdevt-imports", broker=config.redis_url.get_secret_value())
celery.conf.update(
    task_default_queue="knotdevt-imports",
    task_ignore_result=True,
    task_serializer="json",
    accept_content=["json"],
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    beat_schedule={
        "recover-imports": {"task": "knotdevt.imports.dispatch", "schedule": 15.0}
    },
)


@celery.task(name="knotdevt.execute")
def import_only(job_id: str):
    with Session(engine()) as db:
        job = db.get(Job, UUID(job_id))
        if job is None or job.kind != "import" or job.queue != "knotdevt-imports":
            return
    execute(job_id)


@celery.task(name="knotdevt.imports.dispatch")
def dispatch_imports():
    with Session(engine()) as db, db.begin():
        now = datetime.now(UTC)
        jobs = db.scalars(
            select(Job)
            .where(
                Job.kind == "import",
                Job.queue == "knotdevt-imports",
                Job.state == "queued",
                Job.dispatch_after <= now,
            )
            .with_for_update(skip_locked=True)
            .limit(20)
        ).all()
        for job in jobs:
            celery.send_task(
                "knotdevt.execute",
                args=[str(job.id)],
                queue="knotdevt-imports",
                retry=False,
            )
            job.dispatch_after = now + timedelta(seconds=15)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "beat":
        schedule = Path(os.environ["LOCALAPPDATA"]) / "KnotDevt/logs/imports-beat"
        celery.start(["beat", "--loglevel=INFO", "--schedule", str(schedule)])
    else:
        celery.worker_main(
            [
                "worker",
                "--pool=solo",
                "--concurrency=1",
                "--queues=knotdevt-imports",
                "--hostname=knotdevt-imports@%h",
                "--loglevel=INFO",
            ]
        )
