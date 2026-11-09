from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import DB, Actor
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
from app.services.imports import queue_import
from app.services.jobs import get_job, job_view
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


@router.get("/projects/{project_id}/sources")
def sources(
    project_id: UUID,
    identity: Actor,
    db: DB,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> SourcesPage:
    return list_sources(
        db, require_project(db, project_id, identity.user.id), offset, limit
    )


@router.get("/sources/{source_id}")
def read_source(source_id: UUID, identity: Actor, db: DB) -> SourceView:
    source, _ = source_context(db, source_id, identity.user.id)
    revision = latest_revision(db, source.id)
    if revision is None:
        raise HTTPException(404, "Source not found")
    return source_view(source, revision)


@router.put("/sources/{source_id}/policy", status_code=204)
def source_policy(source_id: UUID, body: SourcePolicy, identity: Actor, db: DB) -> None:
    manage_source(db, source_id, identity.user.id, body)


@router.delete("/sources/{source_id}", status_code=204)
def delete_source(source_id: UUID, identity: Actor, db: DB) -> None:
    manage_source(db, source_id, identity.user.id, None)
