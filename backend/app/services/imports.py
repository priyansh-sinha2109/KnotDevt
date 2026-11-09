import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.sources import (
    ImportPayload,
    ImportResult,
    Job,
    Source,
    SourceAccessRule,
    SourceRevision,
)
from app.repositories.sources import latest_revision, lock_project
from app.schemas.sources import IMPORT_INPUT, ImportInput, IssueImport
from app.services.access import EDITORS, ProjectAccess, audit, require_project


class JobFailure(Exception):
    """Expected job error with a safe public code."""


def queue_import(
    db: Session, access: ProjectAccess, raw: bytes, key: str | None
) -> Job:
    access.require(EDITORS)
    digest = hashlib.sha256(raw).hexdigest()
    lock_project(db, access.project.id)
    access = require_project(db, access.project.id, access.user_id)
    access.require(EDITORS)
    if key is not None:
        existing = db.scalar(
            select(Job).where(
                Job.project_id == access.project.id,
                Job.actor_id == access.user_id,
                Job.kind == "import",
                Job.key == key,
            )
        )
        if existing is not None:
            if existing.input_hash != digest:
                raise HTTPException(409, "Idempotency key already used")
            return existing
    job = Job(
        project_id=access.project.id,
        actor_id=access.user_id,
        kind="import",
        key=key,
        input_hash=digest,
    )
    db.add(job)
    db.flush()
    db.add(ImportPayload(job_id=job.id, original=raw))
    audit(db, access.user_id, "import.queued", project=access.project, target_id=job.id)
    db.commit()
    return job


def run_import(db: Session, job: Job) -> None:
    lock_project(db, job.project_id)
    try:
        access = require_project(db, job.project_id, job.actor_id)
        access.require(EDITORS)
    except HTTPException:
        raise JobFailure("access_changed") from None
    payload = db.get(ImportPayload, job.id)
    if payload is None:
        raise JobFailure("invalid_import")
    parsed = IMPORT_INPUT.validate_json(payload.original)
    import_revisions(db, access, job, parsed)
    audit(
        db, job.actor_id, "import.completed", project=access.project, target_id=job.id
    )


def import_revisions(
    db: Session, access: ProjectAccess, job: Job, batch: ImportInput
) -> None:
    for entry in batch.events if isinstance(batch, IssueImport) else batch.notes:
        source = db.scalar(
            select(Source).where(
                Source.project_id == job.project_id,
                Source.provider == batch.provider,
                Source.kind == batch.kind,
                Source.original_id == entry.source_id,
            )
        )
        if source is None:
            source = Source(
                project_id=job.project_id,
                owner_id=access.user_id,
                provider=batch.provider,
                kind=batch.kind,
                original_id=entry.source_id,
                restricted=entry.access == "restricted",
            )
            db.add(source)
            db.flush()
            if source.restricted:
                db.add(SourceAccessRule(source_id=source.id, user_id=access.user_id))
        elif source.deleted_at is not None or source.owner_id != access.user_id:
            raise JobFailure("source_unavailable")
        elif source.restricted != (entry.access == "restricted"):
            raise JobFailure("policy_conflict")

        canonical = json.dumps(
            entry.model_dump(mode="json", exclude={"access"}), sort_keys=True
        ).encode()
        digest = hashlib.sha256(canonical).hexdigest()
        revision = db.scalar(
            select(SourceRevision).where(
                SourceRevision.source_id == source.id,
                SourceRevision.content_hash == digest,
            )
        )
        duplicate = revision is not None
        if revision is None:
            latest = latest_revision(db, source.id)
            revision = SourceRevision(
                source_id=source.id,
                import_job_id=job.id,
                ordinal=latest.ordinal + 1 if latest else 1,
                content_hash=digest,
                author=entry.author,
                event_at=entry.event_at,
                reference=entry.reference,
                event_type=entry.event_type,
                excerpt=entry.text,
                related_ids=entry.related_ids,
            )
            db.add(revision)
            db.flush()
        db.add(
            ImportResult(job_id=job.id, revision_id=revision.id, duplicate=duplicate)
        )
