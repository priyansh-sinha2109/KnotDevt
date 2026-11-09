from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.evidence import ClaimRevision, EvidenceLink
from app.db.handover import DraftClaim, Rubric
from app.schemas.agents import RubricProposal
from app.schemas.critical_gaps import CriticalGapReview

CRITICAL_KINDS = frozenset({"prerequisite", "blocker"})
CITATION_FLAGS = frozenset(
    {
        "invalid_or_ambiguous_citation",
        "supporting_evidence_missing",
        "contradictory_evidence",
    }
)


def validate_gap_review(
    db: Session,
    review: CriticalGapReview,
    claims: list[tuple[ClaimRevision, DraftClaim]],
    source_revision_ids: list[str],
) -> None:
    sources = {UUID(value) for value in source_revision_ids}
    if review.reviewed_source_revision_ids != sources:
        raise HTTPException(
            409, "Critical gap review must cover the exact source snapshot"
        )
    if any(item.source_revision_id not in sources for item in review.additional_gaps):
        raise HTTPException(
            422, "Critical gap references evidence outside the draft snapshot"
        )

    decisions = {item.claim_revision_id: item for item in review.claims}
    if decisions.keys() != {claim.id for claim, _ in claims}:
        raise HTTPException(
            409, "Critical gap review must cover every current claim revision"
        )

    for claim, link in claims:
        disposition = decisions[claim.id].disposition
        if claim.kind in CRITICAL_KINDS and disposition == "non_blocking":
            raise HTTPException(
                409, "Reclassify a critical claim before marking it non-blocking"
            )
        if disposition == "resolved":
            if claim.status != "resolved" or CITATION_FLAGS.intersection(link.flags):
                raise HTTPException(
                    409, "Critical resolution requires a resolved claim with evidence"
                )
            contradiction = db.scalar(
                select(EvidenceLink.id)
                .where(
                    EvidenceLink.claim_revision_id == claim.id,
                    EvidenceLink.relation == "contradicts",
                )
                .limit(1)
            )
            if contradiction is not None:
                raise HTTPException(
                    409, "Critical resolution has contradictory evidence"
                )


def stored_gap_review(db: Session, version_id: UUID) -> CriticalGapReview | None:
    spec = db.scalar(select(Rubric.spec).where(Rubric.version_id == version_id))
    if spec is None or "critical_gap_review" not in spec:
        return None
    try:
        return CriticalGapReview.model_validate(spec["critical_gap_review"])
    except ValidationError:
        return None


def approved_rubric(spec: dict[str, object]) -> RubricProposal:
    return RubricProposal.model_validate(
        {key: value for key, value in spec.items() if key != "critical_gap_review"}
    )
