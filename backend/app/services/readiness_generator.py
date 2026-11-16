"""Deterministic, evidence-bound readiness assessment generation."""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.evidence import ClaimRevision, EvidenceLink
from app.db.handover import Version, VersionClaim
from app.schemas.agents import RubricProposal

DIMENSIONS = ("action", "prerequisites", "evidence", "escalation")


def generate_for_version(db: Session, version: Version) -> dict[str, object]:
    rows = db.execute(
        select(ClaimRevision, EvidenceLink.source_revision_id)
        .join(VersionClaim, VersionClaim.claim_revision_id == ClaimRevision.id)
        .join(EvidenceLink, EvidenceLink.claim_revision_id == ClaimRevision.id)
        .where(VersionClaim.version_id == version.id, EvidenceLink.relation != "context")
        .order_by(VersionClaim.position, EvidenceLink.start_offset)
    ).all()
    selected: dict[str, tuple[ClaimRevision, UUID]] = {}
    for claim, source_id in rows:
        dimension = _dimension_for(claim.kind, claim.status)
        if dimension and dimension not in selected:
            selected[dimension] = (claim, source_id)
    missing = [dimension for dimension in DIMENSIONS if dimension not in selected]
    if missing:
        return {"configured": False, "generation_status": "needs_information", "missing_dimensions": missing}
    questions = []
    for dimension in DIMENSIONS:
        claim, source_id = selected[dimension]
        statement = claim.statement.strip()
        questions.append({
            "dimension": dimension,
            "prompt": _prompt(dimension),
            "choices": [statement, _distractor(dimension)],
            "correct_choice": 0,
            "weight": 25,
            "explanation": f"The approved handover records: {statement}",
            "evidence_revision_ids": [str(source_id)],
        })
    rubric = RubricProposal(title="Evidence-grounded handover readiness", threshold=80, questions=questions)
    return {**rubric.model_dump(mode="json"), "configured": True, "generation_status": "ready", "missing_dimensions": []}


def _dimension_for(kind: str, status: str) -> str | None:
    if kind in {"next_action", "work_item"} and status not in {"resolved", "rejected"}:
        return "action"
    if kind in {"prerequisite", "blocker", "risk"} and status not in {"resolved", "rejected"}:
        return "prerequisites"
    if kind in {"decision", "overview"} and status != "rejected":
        return "evidence"
    if kind in {"owner", "contact", "blocker"} and status not in {"resolved", "rejected"}:
        return "escalation"
    return None


def _prompt(dimension: str) -> str:
    return {
        "action": "Which action is explicitly recorded as the next step in this handover?",
        "prerequisites": "Which prerequisite or unresolved condition is recorded for this handover?",
        "evidence": "Which statement matches the approved project evidence?",
        "escalation": "Which documented responsibility or escalation item should the recipient follow?",
    }[dimension]


def _distractor(dimension: str) -> str:
    return {
        "action": "Declare the work complete without checking the recorded next step.",
        "prerequisites": "Assume all dependencies are satisfied without verification.",
        "evidence": "Treat an unrecorded assumption as a confirmed project fact.",
        "escalation": "Invent an owner or escalation contact not present in the handover.",
    }[dimension]
