from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.provider import generate
from app.core.config import settings
from app.db.handover import Rubric
from app.db.readiness import Attempt, AttemptAdvisory
from app.db.sources import Job
from app.schemas.agents import RubricProposal, ShortText
from app.schemas.sources import StrictModel
from app.services.critical_gaps import approved_rubric
from app.services.imports import JobFailure
from app.services.versions import version_access, version_state


class AdvisoryInput(StrictModel):
    task: str
    rubric: RubricProposal
    response: str


class AdvisoryOutput(StrictModel):
    feedback: ShortText


def run_advice(db: Session, job: Job) -> None:
    advice = db.scalar(select(AttemptAdvisory).where(AttemptAdvisory.job_id == job.id))
    if advice is None:
        raise JobFailure("assessment_unavailable")
    attempt = db.get(Attempt, advice.attempt_id)
    if (
        attempt is None
        or attempt.recipient_id != job.actor_id
        or attempt.explanation is None
    ):
        raise JobFailure("assessment_unavailable")
    try:
        version, _ = version_access(
            db, attempt.version_id, job.actor_id, assigned_only=True
        )
        if version_state(db, version, job.actor_id) != "approved":
            raise JobFailure("assessment_unavailable")
    except HTTPException:
        raise JobFailure("assessment_unavailable") from None
    rubric = db.get(Rubric, attempt.rubric_id)
    if rubric is None:
        raise JobFailure("assessment_unavailable")
    if advice.model == "deterministic-fixture":
        advice.feedback = (
            "Compare the explanation with the approved rubric and safety gates."
        )
        return
    cfg = settings()
    try:
        value = generate(
            "readiness_coach",
            AdvisoryInput(
                task=version.task,
                rubric=approved_rubric(rubric.spec),
                response=attempt.explanation,
            ),
            AdvisoryOutput,
            advice.model,
            cfg.agent_timeout_seconds,
            min(cfg.agent_token_limit, 750),
            instruction=(
                "Offer short advisory feedback on the recipient's explanation for this "
                "scoped rehearsal. Do not grade, assign a score, declare readiness, or "
                "override any safety gate. The reviewer can correct this advice."
            ),
        )
    except Exception:
        raise JobFailure("advisory_unavailable") from None
    advice.feedback = value.feedback
