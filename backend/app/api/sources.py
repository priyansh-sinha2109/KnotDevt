from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from pydantic import ValidationError
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import DB, Actor
from app.db.sources import SourceRevision
from app.repositories.sources import latest_revision
from app.schemas.sources import (
    IMPORT_INPUT,
    MAX_IMPORT_BYTES,
    JobView,
    SourcePolicy,
    SourcesPage,
    SourceView,
    import_schema,
)
from app.services.access import EDITORS, require_project
from app.services.github_issue import GitHubSnapshot, public_issue
from app.services.imports import queue_import
from app.services.jobs import get_job, job_view, retry_import
from app.services.sources import (
    list_sources,
    manage_source,
    source_context,
    source_view,
)

router = APIRouter(tags=["sources", "imports"])


@router.post(
    "/projects/{project_id}/imports",
    status_code=202,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": import_schema()}},
        }
    },
)
async def import_sources(
    project_id: UUID,
    request: Request,
    identity: Actor,
    db: DB,
    key: Annotated[
        str | None,
        Header(alias="Idempotency-Key", max_length=128, pattern=r"^[A-Za-z0-9._:-]+$"),
    ] = None,
) -> JobView:
    def authorized() -> None:
        require_project(db, project_id, identity.user.id).require(EDITORS)

    await run_in_threadpool(authorized)
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/json"
    ):
        raise HTTPException(415, "Expected application/json")
    raw = bytearray()
    async for chunk in request.stream():
        if len(chunk) > MAX_IMPORT_BYTES - len(raw):
            raise HTTPException(413, "Import exceeds the size limit")
        raw.extend(chunk)
    try:
        IMPORT_INPUT.validate_json(raw)
    except ValidationError:
        raise HTTPException(422, "Invalid source import document") from None

    def accept() -> JobView:
        access = require_project(db, project_id, identity.user.id)
        return job_view(queue_import(db, access, bytes(raw), key))

    return await run_in_threadpool(accept)


@router.get("/jobs/{job_id}")
def inspect_job(job_id: UUID, identity: Actor, db: DB) -> JobView:
    return get_job(db, job_id, identity.user.id)


@router.post("/jobs/{job_id}/retry")
def retry_job(job_id: UUID, identity: Actor, db: DB) -> JobView:
    return retry_import(db, job_id, identity.user.id)


@router.get("/projects/{project_id}/sources")
def sources(
    project_id: UUID,
    identity: Actor,
    db: DB,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    query: Annotated[str | None, Query(min_length=1, max_length=160)] = None,
    provider: Annotated[str | None, Query(pattern=r"^[a-z][a-z0-9_-]{0,63}$")] = None,
    event_type: Annotated[str | None, Query(pattern=r"^[a-z][a-z0-9_-]{0,31}$")] = None,
) -> SourcesPage:
    return list_sources(
        db,
        require_project(db, project_id, identity.user.id),
        offset,
        limit,
        query,
        provider,
        event_type,
    )


@router.get("/sources/{source_id}")
def read_source(source_id: UUID, identity: Actor, db: DB) -> SourceView:
    source, _ = source_context(db, source_id, identity.user.id)
    revision = latest_revision(db, source.id)
    if revision is None:
        raise HTTPException(404, "Source not found")
    return source_view(source, revision)


@router.post("/sources/{source_id}/public-issue")
def preview_public_issue(
    source_id: UUID, identity: Actor, db: DB, response: Response
) -> GitHubSnapshot:
    source, access = source_context(db, source_id, identity.user.id)
    access.require(EDITORS)
    revision = latest_revision(db, source.id)
    if revision is None:
        raise HTTPException(404, "Source not found")
    response.headers["Cache-Control"] = "no-store"
    return public_issue(revision.reference)


@router.put("/sources/{source_id}/policy", status_code=204)
def source_policy(source_id: UUID, body: SourcePolicy, identity: Actor, db: DB) -> None:
    manage_source(db, source_id, identity.user.id, body)


@router.delete("/sources/{source_id}", status_code=204)
def delete_source(source_id: UUID, identity: Actor, db: DB) -> None:
    manage_source(db, source_id, identity.user.id, None)


@router.get("/sources/{source_id}/revisions")
def source_revisions(source_id: UUID, identity: Actor, db: DB) -> SourcesPage:
    source, _ = source_context(db, source_id, identity.user.id)
    rows = db.scalars(
        select(SourceRevision)
        .where(SourceRevision.source_id == source.id)
        .order_by(SourceRevision.ordinal.desc())
        .limit(100)
    ).all()
    return SourcesPage(
        items=[source_view(source, row) for row in rows], next_offset=None
    )


@router.get("/sources/{source_id}/claims")
def source_claims(source_id: UUID, identity: Actor, db: DB) -> dict[str, object]:
    from app.db.evidence import Claim, ClaimRevision, EvidenceLink
    from app.repositories.evidence import claim_visible, is_current_claim

    source, _ = source_context(db, source_id, identity.user.id)
    rows = db.execute(
        select(ClaimRevision.claim_id, ClaimRevision.statement)
        .join(Claim, Claim.id == ClaimRevision.claim_id)
        .join(EvidenceLink, EvidenceLink.claim_revision_id == ClaimRevision.id)
        .join(SourceRevision, SourceRevision.id == EvidenceLink.source_revision_id)
        .where(
            SourceRevision.source_id == source.id,
            is_current_claim(),
            claim_visible(source.project_id, identity.user.id),
        )
        .distinct()
        .limit(50)
    ).all()
    return {"items": [{"id": str(row[0]), "statement": row[1]} for row in rows]}
