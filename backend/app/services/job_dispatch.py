"""Best-effort post-commit delivery; PostgreSQL remains the durable job outbox."""

import logging
from uuid import UUID

logger = logging.getLogger(__name__)


def notify_job(job_id: UUID) -> None:
    # Lazy import avoids the worker -> services -> worker import cycle.
    from sqlalchemy.orm import Session

    from app.db.session import engine
    from app.db.sources import Job
    from app.workers.celery_app import EXECUTE, celery

    try:
        with Session(engine()) as db:
            job = db.get(Job, job_id)
            if job is None or job.queue is None:
                return
            queue = job.queue
        celery.send_task(EXECUTE, args=[str(job_id)], queue=queue, retry=False)
    except Exception as exc:
        # Acceptance has already committed. Do not report failure and invite a
        # duplicate submission. Beat/dispatch retries the durable queued row.
        logger.warning("job_dispatch_deferred error_type=%s", type(exc).__name__)
