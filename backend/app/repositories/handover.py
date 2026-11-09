from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.evidence import Claim, ClaimRevision
from app.db.handover import DraftClaim, VersionClaim
from app.repositories.evidence import is_current_claim


def draft_claims(db: Session, draft_id: UUID) -> list[tuple[ClaimRevision, DraftClaim]]:
    rows = db.execute(
        select(ClaimRevision, DraftClaim)
        .select_from(DraftClaim)
        .join(Claim, Claim.id == DraftClaim.claim_id)
        .join(ClaimRevision, is_current_claim())
        .where(DraftClaim.draft_id == draft_id)
        .order_by(DraftClaim.position)
    ).all()
    return [(row[0], row[1]) for row in rows]


def version_claims(db: Session, version_id: UUID) -> list[ClaimRevision]:
    return list(
        db.scalars(
            select(ClaimRevision)
            .join(VersionClaim, VersionClaim.claim_revision_id == ClaimRevision.id)
            .where(VersionClaim.version_id == version_id)
            .order_by(VersionClaim.position)
        )
    )
