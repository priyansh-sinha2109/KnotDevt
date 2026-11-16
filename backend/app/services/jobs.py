from typing import cast
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.agent_inputs import AgentRequest
from app.db.handover import Draft, Version
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
from app.services.provider_authorization import authorized


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
    result = job_view(
        job,
        [
            ImportedRevision(source_id=row[0], revision_id=row[1], duplicate=row[2])
            for row in results
        ],
    )
    if job.kind == "agents" and job.state == "queued":
        request = db.get(AgentRequest, job.id)
        if request is not None and not authorized(job, request):
            result.phase = "awaiting_provider_authorization"
            result.next_action = "wait"
    if job.kind == "agents" and job.state == "succeeded":
        resume = db.scalar(
            select(Job)
            .join(Version, Version.resume_job_id == Job.id)
            .join(Draft, Draft.id == Version.draft_id)
            .where(Draft.agent_job_id == job_id)
            .order_by(Version.number.desc())
            .limit(1)
        )
        if resume is not None:
            result.phase = (
                "succeeded"
                if resume.state == "succeeded"
                else "reconciliation_failed"
                if resume.state == "failed"
                else "reconciling"
            )
            result.next_action = (
                "none"
                if resume.state == "succeeded"
                else "inspect_error"
                if resume.state == "failed"
                else "wait"
            )
            result.error_code = resume.error_code
    return result


def retry_import(db: Session, job_id: UUID, user_id: UUID) -> JobView:
    from datetime import UTC, datetime

    get_job(db, job_id, user_id)
    job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
    if job is None or job.kind != "import":
        raise HTTPException(404, "Import job not found")
    require_project(db, job.project_id, user_id).require(EDITORS)
    if job.state == "failed":
        if job.error_code != "processing_failed":
            raise HTTPException(
                409, "Correct the import or permissions before submitting again"
            )
        job.state = "queued"
        job.attempts = 0
        job.error_code = None
        job.dispatch_after = datetime.now(UTC)
    result = job_view(job)
    db.commit()
    from app.services.job_dispatch import notify_job

    if job.state == "queued":
        notify_job(job.id)
    return result
