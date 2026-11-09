from typing import cast
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.instructions import VERSION
from app.core.config import settings
from app.db.handover import Rubric, Version
from app.db.readiness import Attempt, AttemptAdvisory, AttemptReview
from app.db.sources import Job
from app.repositories.handover import version_claims
from app.repositories.sources import lock_project
from app.schemas.agents import RubricProposal
from app.schemas.handover import VersionState
from app.schemas.readiness import (
    Advice,
    Assessment,
    AttemptInput,
    PackageReadiness,
    RecipientStatus,
    Rehearsal,
    RehearsalQuestion,
    ReviewInput,
    ReviewView,
    ScoreFeedback,
)
from app.schemas.sources import JobState
from app.services.access import REVIEWERS, ProjectAccess, audit
from app.services.versions import version_access, version_state


def package_readiness(
    db: Session, version: Version, state: VersionState
) -> PackageReadiness:
    if state == "unavailable":
        return PackageReadiness(
            status="access_review_required", gates=["required_access"]
        )
    if state == "withdrawn":
        return PackageReadiness(
            status="stale_or_requires_review", gates=["task_not_approved"]
        )
    if state == "stale":
        return PackageReadiness(
            status="stale_or_requires_review", gates=["stale_evidence"]
        )
    unresolved = any(
        claim.kind in {"prerequisite", "blocker"} and claim.status != "resolved"
        for claim in version_claims(db, version.id)
    )
    if unresolved:
        return PackageReadiness(
            status="blocked_by_project_gap", gates=["critical_prerequisite"]
        )
    return PackageReadiness(status="ready", gates=[])


def rubric_access(
    db: Session,
    rubric_id: UUID,
    user_id: UUID,
    *,
    assigned_only: bool = False,
) -> tuple[Rubric, Version, ProjectAccess]:
    rubric = db.get(Rubric, rubric_id)
    if rubric is None:
        raise HTTPException(404, "Rubric not found")
    try:
        version, access = version_access(
            db, rubric.version_id, user_id, assigned_only=assigned_only
        )
    except HTTPException:
        raise HTTPException(404, "Rubric not found") from None
    return rubric, version, access


def rehearsal(db: Session, rubric_id: UUID, user_id: UUID) -> Rehearsal:
    rubric, version, _ = rubric_access(db, rubric_id, user_id)
    state = version_state(db, version, user_id)
    package = package_readiness(db, version, state)
    if state in {"unavailable", "withdrawn"}:
        return Rehearsal(id=rubric.id, version_id=version.id, package=package)
    spec = RubricProposal.model_validate(rubric.spec)
    return Rehearsal(
        id=rubric.id,
        version_id=version.id,
        package=package,
        title=spec.title,
        threshold=spec.threshold,
        questions=[
            RehearsalQuestion(
                dimension=q.dimension,
                prompt=q.prompt,
                choices=q.choices,
                weight=q.weight,
            )
            for q in spec.questions
        ],
    )


def recipient_status(
    package: PackageReadiness, score: int, threshold: int
) -> RecipientStatus:
    if package.status != "ready":
        return package.status
    return "ready_for_scoped_task" if score >= threshold else "needs_guided_practice"


def submit_attempt(
    db: Session,
    rubric_id: UUID,
    user_id: UUID,
    body: AttemptInput,
) -> tuple[Assessment, bool]:
    _, initial, _ = rubric_access(db, rubric_id, user_id, assigned_only=True)
    lock_project(db, initial.project_id)
    rubric, version, access = rubric_access(db, rubric_id, user_id, assigned_only=True)
    state = version_state(db, version, user_id)
    if state in {"unavailable", "withdrawn"}:
        raise HTTPException(409, "Rehearsal unavailable")
    if body.client_attempt_id is not None:
        existing = db.scalar(
            select(Attempt).where(
                Attempt.rubric_id == rubric_id,
                Attempt.recipient_id == user_id,
                Attempt.client_attempt_id == body.client_attempt_id,
            )
        )
        if existing is not None:
            if (
                existing.answers != body.answers
                or existing.explanation != body.explanation
            ):
                raise HTTPException(409, "Attempt key already used")
            return assessment_view(db, existing, version, state), False

    spec = RubricProposal.model_validate(rubric.spec)
    feedback = []
    for question in spec.questions:
        answer = body.answers.get(question.dimension)
        if answer is not None and answer >= len(question.choices):
            raise HTTPException(422, "Answer does not match a question choice")
        points = question.weight if answer == question.correct_choice else 0
        feedback.append(
            ScoreFeedback(
                dimension=question.dimension,
                points=points,
                weight=question.weight,
                explanation=question.explanation,
            )
        )
    score = sum(item.points for item in feedback)
    package = package_readiness(db, version, state)
    attempt = Attempt(
        rubric_id=rubric.id,
        version_id=version.id,
        recipient_id=user_id,
        client_attempt_id=body.client_attempt_id,
        source_revision_ids=version.source_revision_ids,
        answers=body.answers,
        explanation=body.explanation,
        score=score,
        status=recipient_status(package, score, spec.threshold),
        package_status=package.status,
        gates=package.gates,
        feedback=[item.model_dump(mode="json") for item in feedback],
    )
    db.add(attempt)
    db.flush()
    if body.explanation is not None and state == "approved":
        queue_advice(db, attempt, version)
    audit(
        db, user_id, "readiness.attempted", project=access.project, target_id=attempt.id
    )
    result = assessment_view(db, attempt, version, state)
    db.commit()
    return result, True


def queue_advice(db: Session, attempt: Attempt, version: Version) -> None:
    config = settings()
    job = Job(
        project_id=version.project_id,
        actor_id=attempt.recipient_id,
        kind="readiness_advice",
        input_hash=version.content_hash,
    )
    db.add(job)
    db.flush()
    db.add(
        AttemptAdvisory(
            attempt_id=attempt.id,
            job_id=job.id,
            prompt_version=VERSION,
            model=config.llm_model
            if config.llm_provider == "gemini"
            else "deterministic-fixture",
        )
    )


def assessment_view(
    db: Session,
    attempt: Attempt,
    version: Version,
    state: VersionState,
) -> Assessment:
    package = package_readiness(db, version, state)
    original = cast(RecipientStatus, attempt.status)
    status: RecipientStatus = original if package.status == "ready" else package.status
    result = Assessment(
        id=attempt.id,
        version_id=attempt.version_id,
        rubric_id=attempt.rubric_id,
        recipient_id=attempt.recipient_id,
        attempted_at=attempt.attempted_at,
        status=status,
        package=package,
        review_status="withheld",
    )
    if state in {"unavailable", "withdrawn"}:
        return result
    result.assessed_status = original
    result.score = attempt.score
    result.answers = attempt.answers
    result.explanation = attempt.explanation
    result.feedback = [ScoreFeedback.model_validate(item) for item in attempt.feedback]
    advice = db.get(AttemptAdvisory, attempt.id)
    if advice is not None:
        job = db.get(Job, advice.job_id)
        if job is not None:
            result.advisory = Advice(
                status=cast(JobState, job.state),
                model=advice.model,
                prompt_version=advice.prompt_version,
                feedback=advice.feedback,
            )
    review = db.get(AttemptReview, attempt.id)
    if review is not None:
        result.review = ReviewView(
            reviewer_id=review.reviewer_id,
            feedback=review.feedback,
            reviewed_at=review.reviewed_at,
        )
    result.review_status = "reviewed" if review is not None else "pending"
    return result


def attempt_access(
    db: Session,
    attempt_id: UUID,
    user_id: UUID,
) -> tuple[Attempt, Version, ProjectAccess]:
    attempt = db.get(Attempt, attempt_id)
    if attempt is None:
        raise HTTPException(404, "Attempt not found")
    try:
        version, access = version_access(db, attempt.version_id, user_id)
    except HTTPException:
        raise HTTPException(404, "Attempt not found") from None
    if attempt.recipient_id != user_id and access.role not in REVIEWERS:
        raise HTTPException(404, "Attempt not found")
    return attempt, version, access


def review_attempt(
    db: Session,
    attempt_id: UUID,
    user_id: UUID,
    body: ReviewInput,
) -> Assessment:
    _, version, _ = attempt_access(db, attempt_id, user_id)
    lock_project(db, version.project_id)
    attempt, version, access = attempt_access(db, attempt_id, user_id)
    access.require(REVIEWERS)
    state = version_state(db, version, user_id)
    if state in {"unavailable", "withdrawn"}:
        raise HTTPException(409, "Assessment unavailable")
    review = db.get(AttemptReview, attempt.id)
    if review is None:
        db.add(
            AttemptReview(
                attempt_id=attempt.id, reviewer_id=user_id, feedback=body.feedback
            )
        )
    else:
        review.reviewer_id = user_id
        review.feedback = body.feedback
    audit(
        db, user_id, "readiness.reviewed", project=access.project, target_id=attempt.id
    )
    db.flush()
    result = assessment_view(db, attempt, version, state)
    db.commit()
    return result
