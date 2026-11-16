from uuid import UUID

from fastapi import APIRouter, Response

from app.api.dependencies import DB, Actor
from app.schemas.readiness import Assessment, AttemptInput, ReadinessConfigureInput, Rehearsal, ReviewInput
from app.services.readiness import (
    assessment_view,
    attempt_access,
    rehearsal,
    review_attempt,
    submit_attempt,
    configure_readiness,
)
from app.services.versions import version_state

router = APIRouter(tags=["readiness"])


@router.put("/versions/{version_id}/readiness")
def readiness_configure(
    version_id: UUID,
    body: ReadinessConfigureInput,
    identity: Actor,
    db: DB,
) -> Rehearsal:
    return configure_readiness(db, version_id, identity.user.id, body)


@router.get("/rubrics/{rubric_id}")
def rubric_read(rubric_id: UUID, identity: Actor, db: DB) -> Rehearsal:
    return rehearsal(db, rubric_id, identity.user.id)


@router.post(
    "/rubrics/{rubric_id}/attempts",
    status_code=201,
    responses={200: {"model": Assessment}},
)
def attempt_submit(
    rubric_id: UUID,
    body: AttemptInput,
    response: Response,
    identity: Actor,
    db: DB,
) -> Assessment:
    result, created = submit_attempt(db, rubric_id, identity.user.id, body)
    if not created:
        response.status_code = 200
    return result


@router.get("/attempts/{attempt_id}")
def attempt_read(attempt_id: UUID, identity: Actor, db: DB) -> Assessment:
    attempt, version, _ = attempt_access(db, attempt_id, identity.user.id)
    state = version_state(db, version, identity.user.id)
    return assessment_view(db, attempt, version, state, identity.user.id)


@router.put("/attempts/{attempt_id}/review")
def attempt_review(
    attempt_id: UUID, body: ReviewInput, identity: Actor, db: DB
) -> Assessment:
    return review_attempt(db, attempt_id, identity.user.id, body)
