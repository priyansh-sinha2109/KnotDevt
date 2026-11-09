from typing import cast
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import case, or_, select
from sqlalchemy.orm import Session

from app.db.evidence import Claim, ClaimRelationship, ClaimRevision, EvidenceLink
from app.db.sources import Source, SourceRevision
from app.repositories.evidence import (
    claim_visible,
    get_visible_revision,
    is_current_claim,
)
from app.schemas.evidence import (
    ClaimContent,
    ClaimInput,
    ClaimKind,
    ClaimStatus,
    ClaimSummary,
    EvidenceBranch,
    EvidenceTree,
    EvidenceView,
    LinkKind,
    RelatedClaim,
    Relation,
)
from app.services.access import EDITORS, ProjectAccess, audit, require_project


def summary(revision: ClaimRevision) -> ClaimSummary:
    return ClaimSummary(
        id=revision.claim_id,
        revision_id=revision.id,
        number=revision.number,
        kind=cast(ClaimKind, revision.kind),
        status=cast(ClaimStatus, revision.status),
        statement=revision.statement,
    )


def add_revision(
    db: Session,
    access: ProjectAccess,
    claim: Claim,
    content: ClaimContent,
    reviewer_note: str | None = None,
    context_ids: tuple[UUID, ...] = (),
) -> ClaimRevision:
    revision = ClaimRevision(
        claim_id=claim.id,
        number=claim.current_number,
        kind=content.kind,
        status=content.status,
        statement=content.statement,
        authored_by=access.user_id,
        reviewer_note=reviewer_note,
    )
    db.add(revision)
    db.flush()
    keys: set[tuple[UUID, str, int, int]] = set()
    for item in content.evidence:
        row = get_visible_revision(
            db, access.project.id, access.user_id, item.revision_id
        )
        if row is None or row[1].excerpt[item.start : item.end] != item.quote:
            raise HTTPException(422, "Evidence reference or excerpt is invalid")
        key = (item.revision_id, item.relation, item.start, item.end)
        if key in keys:
            raise HTTPException(422, "Duplicate evidence link")
        keys.add(key)
        db.add(
            EvidenceLink(
                claim_revision_id=revision.id,
                source_revision_id=item.revision_id,
                start_offset=item.start,
                end_offset=item.end,
                relation=item.relation,
            )
        )
    for revision_id in sorted(set(context_ids)):
        row = get_visible_revision(db, access.project.id, access.user_id, revision_id)
        if row is None:
            raise HTTPException(409, "Claim context is unavailable")
        db.add(
            EvidenceLink(
                claim_revision_id=revision.id,
                source_revision_id=revision_id,
                start_offset=0,
                end_offset=len(row[1].excerpt),
                relation="context",
            )
        )
    return revision


def create_claim(
    db: Session, access: ProjectAccess, content: ClaimInput
) -> ClaimSummary:
    access.require(EDITORS)
    claim = Claim(project_id=access.project.id, created_by=access.user_id)
    db.add(claim)
    db.flush()
    revision = add_revision(db, access, claim, content)
    relationships = {(item.target_id, item.relation) for item in content.relationships}
    for target_id, relation in relationships:
        current_claim(db, access, target_id)
        db.add(
            ClaimRelationship(
                origin_id=claim.id, target_id=target_id, relation=relation
            )
        )
    audit(
        db, access.user_id, "claim.created", project=access.project, target_id=claim.id
    )
    db.commit()
    return summary(revision)


def current_claim(db: Session, access: ProjectAccess, claim_id: UUID) -> ClaimRevision:
    revision = db.scalar(
        select(ClaimRevision)
        .join(Claim, is_current_claim())
        .where(
            Claim.id == claim_id,
            Claim.project_id == access.project.id,
            claim_visible(access.project.id, access.user_id),
        )
    )
    if revision is None:
        raise HTTPException(404, "Claim not found")
    return revision


def claim_access(db: Session, claim_id: UUID, user_id: UUID) -> ProjectAccess:
    project_id = db.scalar(select(Claim.project_id).where(Claim.id == claim_id))
    if project_id is None:
        raise HTTPException(404, "Claim not found")
    try:
        access = require_project(db, project_id, user_id)
    except HTTPException:
        raise HTTPException(404, "Claim not found") from None
    access.require(EDITORS)
    return access


def evidence_view(
    link: EvidenceLink, source: Source, revision: SourceRevision
) -> EvidenceView:
    return EvidenceView(
        source_id=source.id,
        revision_id=revision.id,
        original_id=source.original_id,
        provider=source.provider,
        event_type=revision.event_type,
        excerpt=revision.excerpt[link.start_offset : link.end_offset],
        start=link.start_offset,
        end=link.end_offset,
        author=revision.author,
        event_at=revision.event_at,
        imported_at=revision.imported_at,
        reference=revision.reference,
        relation=cast(LinkKind, link.relation),
        support=(
            "supporting"
            if link.relation == "supports"
            else "contradicting"
            if link.relation == "contradicts"
            else "related"
        ),
    )


def citations(
    db: Session, access: ProjectAccess, revision_id: UUID
) -> list[EvidenceView]:
    from app.repositories.sources import can_read_source

    rows = db.execute(
        select(EvidenceLink, Source, SourceRevision)
        .join(SourceRevision, SourceRevision.id == EvidenceLink.source_revision_id)
        .join(Source, Source.id == SourceRevision.source_id)
        .where(
            EvidenceLink.claim_revision_id == revision_id,
            EvidenceLink.relation != "context",
            Source.project_id == access.project.id,
            can_read_source(access.user_id),
        )
        .order_by(SourceRevision.event_at, EvidenceLink.id)
    ).all()
    return [evidence_view(row[0], row[1], row[2]) for row in rows]


def tree(
    db: Session, access: ProjectAccess, claim_id: UUID, offset: int, limit: int
) -> EvidenceTree:
    root = current_claim(db, access, claim_id)
    spans = citations(db, access, root.id)
    branches = [
        EvidenceBranch(evidence=span) for span in spans[offset : offset + limit + 1]
    ]
    remaining = limit + 1 - len(branches)
    if remaining:
        other = case(
            (ClaimRelationship.origin_id == claim_id, ClaimRelationship.target_id),
            else_=ClaimRelationship.origin_id,
        )
        links = db.execute(
            select(ClaimRelationship, ClaimRevision)
            .join(Claim, Claim.id == other)
            .join(ClaimRevision, is_current_claim())
            .where(
                or_(
                    ClaimRelationship.origin_id == claim_id,
                    ClaimRelationship.target_id == claim_id,
                ),
                Claim.project_id == access.project.id,
                claim_visible(access.project.id, access.user_id),
            )
            .order_by(Claim.id, ClaimRelationship.relation, ClaimRelationship.origin_id)
            .offset(max(0, offset - len(spans)))
            .limit(remaining)
        ).all()
        branches.extend(
            EvidenceBranch(
                related_claim=RelatedClaim(
                    claim=summary(row[1]),
                    relation=cast(Relation, row[0].relation),
                    direction="outgoing"
                    if row[0].origin_id == claim_id
                    else "incoming",
                )
            )
            for row in links
        )
    return EvidenceTree(
        root=summary(root),
        branches=branches[:limit],
        next_offset=offset + limit if len(branches) > limit else None,
    )
