import logging
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from celery import Celery  # type: ignore[import-untyped]
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import registry  # noqa: F401
from app.db.session import engine
from app.db.sources import Job
from app.services.agents import run_agents
from app.services.imports import JobFailure, run_import
from app.services.readiness_advice import run_advice
from app.services.review_resume import resume_review

logger = logging.getLogger(__name__)
DISPATCH = "knotdevt.dispatch"
EXECUTE = "knotdevt.execute"
celery = Celery("knotdevt", broker=settings().redis_url.get_secret_value())
celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    broker_connection_timeout=3,
    beat_schedule={"recover-durable-jobs": {"task": DISPATCH, "schedule": 3.0}},
)


def dispatch() -> None:
    with Session(engine()) as db, db.begin():
        now = cast(datetime, db.scalar(select(func.clock_timestamp())))
        jobs = db.scalars(
            select(Job)
            .where(
                Job.state == "queued",
                Job.dispatch_after <= now,
            )
            .order_by(Job.dispatch_after)
            .limit(20)
            .with_for_update(skip_locked=True)
        ).all()
        for job in jobs:
            celery.send_task(EXECUTE, args=[str(job.id)], retry=False)
            job.dispatch_after = now + timedelta(seconds=15)


def execute(job_id: str) -> None:
    with Session(engine()) as db, db.begin():
        job = db.scalar(
            select(Job).where(Job.id == UUID(job_id)).with_for_update(key_share=True)
        )
        if job is None or job.state != "queued":
            return
        job.attempts += 1
        try:
            with db.begin_nested():
                if job.kind == "import":
                    run_import(db, job)
                elif job.kind == "agents":
                    run_agents(db, job)
                elif job.kind == "review_resume":
                    resume_review(db, job)
                elif job.kind == "readiness_advice":
                    run_advice(db, job)
                else:
                    raise JobFailure("unknown_job")
        except JobFailure as exc:
            job.state = "failed"
            job.error_code = str(exc)
        except Exception as exc:
            logger.warning(
                "job_failure job_id=%s error_type=%s", job_id, type(exc).__name__
            )
            if job.attempts >= 3:
                job.state = "failed"
                job.error_code = "processing_failed"
            else:
                job.dispatch_after = datetime.now(UTC) + timedelta(seconds=3)
        else:
            job.state = "succeeded"


celery.task(name=DISPATCH)(dispatch)
celery.task(name=EXECUTE)(execute)
