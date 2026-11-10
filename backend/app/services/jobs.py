from typing import cast
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.sources import ImportResult, Job, Source, SourceRevision
from app.repositories.sources import can_read_source
from app.schemas.sources import (
    ImportedRevision,
    JobNextAction,
    JobPhase,
    JobState,
    JobView,
)
from app.services.access import EDITORS, require_project


def job_view(job: Job, revisions: list[ImportedRevision] | None = None) -> JobView:
    phase: JobPhase
    next_action: JobNextAction
    if job.state == "failed":
        phase, next_action = "failed", "inspect_error"
    elif job.state == "succeeded" and job.kind == "agents":
        phase, next_action = "awaiting_human_review", "review"
    elif job.state == "succeeded":
        phase, next_action = "succeeded", "none"
    elif job.attempts:
        phase, next_action = "waiting_retry", "wait"
    else:
        phase, next_action = "queued", "wait"
    return JobView(
        id=job.id,
        project_id=job.project_id,
        kind=job.kind,
        state=cast(JobState, job.state),
        phase=phase,
        next_action=next_action,
        attempt_count=job.attempts,
        next_retry_at=job.dispatch_after if phase == "waiting_retry" else None,
        created_at=job.created_at,
        error_code=job.error_code,
        revisions=revisions or [],
    )


def get_job(db: Session, job_id: UUID, user_id: UUID) -> JobView:
    job = db.scalar(select(Job).where(Job.id == job_id, Job.actor_id == user_id))
    if job is None:
        raise HTTPException(404, "Job not found")
    access = require_project(db, job.project_id, user_id)
    access.require(EDITORS)
    results = db.execute(
        select(Source.id, SourceRevision.id, ImportResult.duplicate)
        .select_from(ImportResult)
        .join(SourceRevision, SourceRevision.id == ImportResult.revision_id)
        .join(Source, Source.id == SourceRevision.source_id)
        .where(
            ImportResult.job_id == job_id,
            Source.project_id == job.project_id,
            can_read_source(user_id),
        )
        .order_by(Source.id)
    ).all()
    return job_view(
        job,
        [
            ImportedRevision(source_id=row[0], revision_id=row[1], duplicate=row[2])
            for row in results
        ],
    )
