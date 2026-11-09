from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.dependencies import DB, Actor
from app.schemas.evidence import ClaimInput, ClaimSummary, EvidenceOutline, EvidenceTree
from app.services.access import require_project
from app.services.evidence import claim_access, create_claim, tree

router = APIRouter(tags=["evidence"])
Offset = Annotated[int, Query(ge=0, le=100_000)]
Limit = Annotated[int, Query(ge=1, le=199)]


@router.post("/projects/{project_id}/claims", status_code=201)
def create(project_id: UUID, body: ClaimInput, identity: Actor, db: DB) -> ClaimSummary:
    return create_claim(db, require_project(db, project_id, identity.user.id), body)


@router.get("/claims/{claim_id}/tree")
def evidence_tree(
    claim_id: UUID, identity: Actor, db: DB, offset: Offset = 0, limit: Limit = 199
) -> EvidenceTree:
    return tree(
        db, claim_access(db, claim_id, identity.user.id), claim_id, offset, limit
    )


@router.get("/claims/{claim_id}/outline")
def outline(
    claim_id: UUID, identity: Actor, db: DB, offset: Offset = 0, limit: Limit = 199
) -> EvidenceOutline:
    result = evidence_tree(claim_id, identity, db, offset, limit)
    lines = []
    for branch in result.branches:
        if branch.evidence is not None:
            evidence = branch.evidence
            lines.append(
                f"{evidence.relation} · {evidence.original_id} · {evidence.excerpt}"
            )
        if branch.related_claim is not None:
            related = branch.related_claim
            lines.append(
                f"{related.direction} {related.relation} · {related.claim.statement}"
            )
    return EvidenceOutline(
        claim=result.root, lines=lines, next_offset=result.next_offset
    )
