from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.evidence import ClaimRelationship
from app.db.handover import Draft, DraftClaim
from app.repositories.handover import version_claims
from app.schemas.evidence import Relation
from app.schemas.trace import ContextTrace, TraceClaim, TraceEdge
from app.services.evidence import citations, claim_access, summary, tree
from app.services.versions import version_access, version_state


def context_trace(
    db: Session,
    claim_id: UUID,
    user_id: UUID,
    version_id: UUID | None,
) -> ContextTrace:
    result = (
        approved_trace(db, claim_id, user_id, version_id)
        if version_id is not None
        else current_trace(db, claim_id, user_id)
    )
    if result.selected is None:
        return result

    selected = result.selected
    lines = [f"{selected.claim.status} · {selected.claim.statement}"]
    for item in result.timeline:
        if item.claim.id != claim_id:
            lines.append(f"{item.claim.status} · {item.claim.statement}")
        lines.extend(
            f"{row.original_id} · {row.event_at.isoformat()} · "
            f"{row.relation} · {row.excerpt}"
            for row in item.evidence
        )
    lines.extend(f"Unresolved · {item}" for item in result.unresolved)
    result.outline = lines
    return result


def chronological(items: list[TraceClaim]) -> list[TraceClaim]:
    return sorted(
        items,
        key=lambda item: (
            min(
                (row.event_at for row in item.evidence),
                default=datetime.max.replace(tzinfo=UTC),
            ),
            item.claim.id,
        ),
    )


def current_trace(db: Session, claim_id: UUID, user_id: UUID) -> ContextTrace:
    access = claim_access(db, claim_id, user_id)
    result = tree(db, access, claim_id, 0, 64)
    selected = TraceClaim(claim=result.root, evidence=[])
    related: dict[UUID, TraceClaim] = {}
    edges = []
    for branch in result.branches:
        if branch.evidence is not None:
            selected.evidence.append(branch.evidence)
        if branch.related_claim is not None:
            link = branch.related_claim
            other_id = link.claim.id
            if other_id not in related:
                related[other_id] = TraceClaim(
                    claim=link.claim,
                    evidence=citations(db, access, link.claim.revision_id),
                )
            origin, target = (
                (claim_id, other_id)
                if link.direction == "outgoing"
                else (other_id, claim_id)
            )
            edges.append(
                TraceEdge(origin_id=origin, target_id=target, relation=link.relation)
            )
    unresolved = db.scalar(
        select(Draft.unresolved)
        .join(DraftClaim, DraftClaim.draft_id == Draft.id)
        .where(DraftClaim.claim_id == claim_id, Draft.project_id == access.project.id)
    )
    return ContextTrace(
        status="current",
        selected=selected,
        timeline=chronological([selected, *related.values()]),
        relationships=edges,
        unresolved=unresolved or [],
    )


def approved_trace(
    db: Session,
    claim_id: UUID,
    user_id: UUID,
    version_id: UUID,
) -> ContextTrace:
    version, access = version_access(db, version_id, user_id)
    state = version_state(db, version, user_id)
    if state in {"unavailable", "withdrawn"}:
        return ContextTrace(version_id=version_id, status=state)

    revisions = {item.claim_id: item for item in version_claims(db, version_id)}
    if claim_id not in revisions:
        raise HTTPException(404, "Claim not found")
    trace = {
        key: TraceClaim(claim=summary(item), evidence=citations(db, access, item.id))
        for key, item in revisions.items()
    }
    links = db.scalars(
        select(ClaimRelationship)
        .where(
            ClaimRelationship.origin_id.in_(revisions),
            ClaimRelationship.target_id.in_(revisions),
        )
        .order_by(
            ClaimRelationship.origin_id,
            ClaimRelationship.target_id,
            ClaimRelationship.relation,
        )
    )
    return ContextTrace(
        version_id=version_id,
        status=state,
        selected=trace[claim_id],
        timeline=chronological(list(trace.values())),
        unresolved=version.unresolved,
        relationships=[
            TraceEdge(
                origin_id=row.origin_id,
                target_id=row.target_id,
                relation=cast(Relation, row.relation),
            )
            for row in links
        ],
    )
