import logging
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from celery import Celery  # type: ignore[import-untyped]
from fastapi import HTTPException
from kombu import Queue
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import registry  # noqa: F401
from app.db.agent_inputs import AgentRequest
from app.db.handover import Version
from app.db.session import engine
from app.db.sources import Job
from app.services.access import require_project
from app.services.agents import run_agents
from app.services.imports import (
    MAX_TRANSIENT_JOB_ATTEMPTS,
    JobFailure,
    TransientJobFailure,
    run_import,
)
from app.services.provider_authorization import authorized
from app.services.readiness_advice import run_advice
from app.services.review_resume import resume_review

logger = logging.getLogger(__name__)
DISPATCH = "knotdevt.dispatch"
EXECUTE = "knotdevt.execute"
celery = Celery("knotdevt", broker=settings().redis_url.get_secret_value())
celery.conf.update(
    task_default_queue=settings().job_queue,
    task_queues=(Queue(settings().job_queue), Queue("knotdevt-connectors")),
    task_routes={
        "knotdevt.connectors.sync": {"queue": "knotdevt-connectors"},
        "knotdevt.connectors.dispatch": {"queue": "knotdevt-connectors"},
    },
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    broker_connection_timeout=3,
    beat_schedule={
        "recover-durable-jobs": {"task": DISPATCH, "schedule": 3.0},
        "recover-connector-syncs": {
            "task": "knotdevt.connectors.dispatch",
            "schedule": 15.0,
            "options": {"queue": "knotdevt-connectors"},
        },
    },
)


def dispatch(job_ids: list[str] | None = None) -> None:
    selected = [UUID(value) for value in job_ids] if job_ids is not None else None
    with Session(engine()) as db, db.begin():
        now = cast(datetime, db.scalar(select(func.clock_timestamp())))
        # Recover legacy exhausted resumes only when backed by a committed approval.
        recoverable = db.scalars(
            select(Job)
            .join(Version, Version.resume_job_id == Job.id)
            .where(
                Job.kind == "review_resume",
                Job.queue == settings().job_queue,
                Job.state == "failed",
                Job.error_code == "processing_failed",
                Job.actor_id == Version.approved_by,
                Job.project_id == Version.project_id,
                *([Job.id.in_(selected)] if selected is not None else []),
            )
            .with_for_update(skip_locked=True, of=Job)
            .limit(20)
        ).all()
        for job in recoverable:
            job.state = "queued"
            job.error_code = "checkpoint_retry_scheduled"
            job.dispatch_after = now
        jobs = db.scalars(
            select(Job)
            .where(
                Job.state == "queued",
                Job.queue == settings().job_queue,
                *(
                    [
                        or_(
                            Job.kind.not_in(("agents", "readiness_advice")),
                            (
                                Job.id.in_(
                                    [
                                        settings().gemini_free_job_id,
                                        settings().openrouter_free_job_id,
                                        settings().groq_free_job_id,
                                    ]
                                )
                            )
                            & (Job.attempts == 0),
                        )
                    ]
                    if not settings().live_ai_authorized
                    and settings().llm_provider != "fake"
                    else []
                ),
                Job.dispatch_after <= now,
                *([Job.id.in_(selected)] if selected is not None else []),
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
        # Wrong-queue and historical messages must never change their job rows.
        if job.queue != settings().job_queue:
            return
        if job.kind == "agents":
            try:
                require_project(db, job.project_id, job.actor_id)
                request = db.get(AgentRequest, job.id)
            except HTTPException:
                # The existing runner records access revocation as a job failure.
                request = None
            if request is not None and not authorized(job, request):
                logger.info("job_awaiting_provider_authorization job_id=%s", job.id)
                return
        if (
            job.kind == "readiness_advice"
            and not settings().live_ai_authorized
            and settings().llm_provider != "fake"
        ):
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
        except TransientJobFailure as exc:
            if job.attempts >= MAX_TRANSIENT_JOB_ATTEMPTS or job.id in {
                settings().gemini_free_job_id,
                settings().openrouter_free_job_id,
                settings().groq_free_job_id,
            }:
                job.state = "failed"
                job.error_code = str(exc)
            else:
                # Keep the durable job queued. The next execution resumes the
                # existing LangGraph checkpoint and only reruns the failed stage.
                job.dispatch_after = datetime.now(UTC) + timedelta(
                    seconds=15 * job.attempts
                )
        except JobFailure as exc:
            job.state = "failed"
            job.error_code = str(exc)
        except Exception as exc:
            logger.warning(
                "job_failure job_id=%s error_type=%s", job_id, type(exc).__name__
            )
            if job.kind == "review_resume":
                # The committed approval is a durable reconciliation intent.
                # Retry infrastructure failures with capped delay, without changing
                # the immutable version or pretending both stores committed together.
                job.error_code = "checkpoint_retry_scheduled"
                job.dispatch_after = datetime.now(UTC) + timedelta(
                    seconds=min(3600, 15 * 2 ** min(job.attempts - 1, 8))
                )
            elif job.attempts >= 3 or job.id in {
                settings().gemini_free_job_id,
                settings().openrouter_free_job_id,
                settings().groq_free_job_id,
            }:
                job.state = "failed"
                job.error_code = "processing_failed"
            else:
                job.dispatch_after = datetime.now(UTC) + timedelta(seconds=3)
        else:
            job.state = "succeeded"
            job.error_code = None


celery.task(name=DISPATCH)(dispatch)
celery.task(name=EXECUTE)(execute)

# Reuse the connector implementation while keeping explicit queue routing.
from app.workers.connector_app import dispatch as dispatch_connectors  # noqa: E402
from app.workers.connector_app import sync as sync_connector  # noqa: E402

celery.task(name="knotdevt.connectors.sync")(sync_connector)
celery.task(name="knotdevt.connectors.dispatch")(dispatch_connectors)
