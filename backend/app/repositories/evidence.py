from uuid import UUID

from sqlalchemy import ColumnElement, and_, exists, select
from sqlalchemy.orm import Session

from app.db.evidence import Claim, ClaimRevision, EvidenceLink
from app.db.sources import Source, SourceRevision
from app.repositories.sources import can_read_source


def get_visible_revision(
    db: Session, project_id: UUID, user_id: UUID, revision_id: UUID
) -> tuple[Source, SourceRevision] | None:
    row = db.execute(
        select(Source, SourceRevision)
        .join(SourceRevision, SourceRevision.source_id == Source.id)
        .where(
            Source.project_id == project_id,
            SourceRevision.id == revision_id,
            can_read_source(user_id),
        )
    ).one_or_none()
    return (row[0], row[1]) if row else None


def claim_visible(project_id: UUID, user_id: UUID) -> ColumnElement[bool]:
    authorized = exists(
        select(1)
        .select_from(SourceRevision)
        .join(Source, Source.id == SourceRevision.source_id)
        .where(
            SourceRevision.id == EvidenceLink.source_revision_id,
            Source.project_id == project_id,
            can_read_source(user_id),
        )
        .correlate(EvidenceLink)
    )
    invisible = exists(
        select(1)
        .select_from(EvidenceLink)
        .where(EvidenceLink.claim_revision_id == ClaimRevision.id, ~authorized)
        .correlate(ClaimRevision)
    )
    return ~invisible


def is_current_claim() -> ColumnElement[bool]:
    return and_(
        ClaimRevision.claim_id == Claim.id, ClaimRevision.number == Claim.current_number
    )
