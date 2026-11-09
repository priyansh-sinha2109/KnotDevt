from uuid import UUID

from fastapi import APIRouter

from app.api.dependencies import DB, Actor
from app.schemas.handover import (
    ApprovalInput,
    ClaimPatch,
    ClaimPatchView,
    DraftInput,
    DraftView,
    VersionView,
)
from app.services.access import require_project
from app.services.drafts import create_draft, draft_view, patch_claim, read_draft
from app.services.versions import approve, version_access, version_view, withdraw

router = APIRouter(tags=["handover"])


@router.post("/projects/{project_id}/drafts", status_code=201)
def draft_create(
    project_id: UUID, body: DraftInput, identity: Actor, db: DB
) -> DraftView:
    return create_draft(
        db, require_project(db, project_id, identity.user.id), body.agent_job_id
    )


@router.get("/drafts/{draft_id}")
def draft_read(draft_id: UUID, identity: Actor, db: DB) -> DraftView:
    draft, _ = read_draft(db, draft_id, identity.user.id)
    return draft_view(db, draft)


@router.patch("/claims/{claim_id}")
def claim_edit(
    claim_id: UUID, body: ClaimPatch, identity: Actor, db: DB
) -> ClaimPatchView:
    return patch_claim(db, identity.user.id, claim_id, body)


@router.post("/drafts/{draft_id}/approve", status_code=201)
def draft_approve(
    draft_id: UUID, body: ApprovalInput, identity: Actor, db: DB
) -> VersionView:
    return approve(db, draft_id, identity.user.id, body)


@router.get("/versions/{version_id}")
def version_read(version_id: UUID, identity: Actor, db: DB) -> VersionView:
    version, access = version_access(db, version_id, identity.user.id)
    return version_view(db, version, access)


@router.post("/versions/{version_id}/withdraw", status_code=204)
def version_withdraw(version_id: UUID, identity: Actor, db: DB) -> None:
    withdraw(db, version_id, identity.user.id)
