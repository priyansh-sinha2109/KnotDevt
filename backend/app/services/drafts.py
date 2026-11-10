from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.agent_inputs import AgentRequest
from app.db.evidence import AgentRun, Claim, ClaimRelationship
from app.db.handover import Draft, DraftClaim
from app.db.sources import Job
from app.repositories.handover import draft_claims
from app.repositories.sources import lock_project
from app.schemas.agents import AgentInput, AuditOutput, ContextBundle, RubricProposal
from app.schemas.handover import ClaimPatch, ClaimPatchView, DraftClaimView, DraftView
from app.services.access import (
    EDITORS,
    REVIEWERS,
    ProjectAccess,
    audit,
    require_project,
)
from app.services.agents import load_context
from app.services.evidence import add_revision, current_claim, summary


def draft_context(
    db: Session,
    draft: Draft,
    user_id: UUID,
    *,
    fresh: bool,
) -> tuple[Job, AgentRequest, ContextBundle]:
    job = db.get(Job, draft.agent_job_id)
    request = db.get(AgentRequest, draft.agent_job_id)
    if job is None or request is None:
        raise HTTPException(409, "Draft evidence is unavailable")
    context = load_context(db, job, request, user_id, fresh=fresh)
    return job, request, context


def read_draft(
    db: Session,
    draft_id: UUID,
    user_id: UUID,
    *,
    lock: bool = False,
) -> tuple[Draft, ProjectAccess, ContextBundle]:
    draft = db.get(Draft, draft_id)
    if draft is None:
        raise HTTPException(404, "Draft not found")
    try:
        access = require_project(db, draft.project_id, user_id)
    except HTTPException:
        raise HTTPException(404, "Draft not found") from None
    if lock:
        lock_project(db, draft.project_id)
        access = require_project(db, draft.project_id, user_id)
        db.refresh(draft, with_for_update=True)
    access.require(EDITORS)
    _, _, context = draft_context(db, draft, user_id, fresh=False)
    return draft, access, context


def draft_view(db: Session, draft: Draft, context: ContextBundle) -> DraftView:
    request = db.get(AgentRequest, draft.agent_job_id)
    if request is None:
        raise HTTPException(409, "Draft evidence is unavailable")
    return DraftView(
        id=draft.id,
        project_id=draft.project_id,
        agent_job_id=draft.agent_job_id,
        revision=draft.revision,
        task=draft.task,
        audience=[UUID(i) for i in draft.audience],
        source_revision_ids=[UUID(i) for i in request.revision_ids],
        source_snapshot=context.evidence,
        claims=[
            DraftClaimView(
                claim=summary(rev), flags=link.flags, reviewer_note=rev.reviewer_note
            )
            for rev, link in draft_claims(db, draft.id)
        ],
        proposed_rubric=RubricProposal.model_validate(draft.proposed_rubric),
        unresolved=draft.unresolved,
    )


def create_draft(db: Session, access: ProjectAccess, agent_job_id: UUID) -> DraftView:
    access.require(EDITORS)
    lock_project(db, access.project.id)
    access = require_project(db, access.project.id, access.user_id)
    access.require(EDITORS)
    job = db.scalar(
        select(Job).where(
            Job.id == agent_job_id,
            Job.project_id == access.project.id,
            Job.kind == "agents",
        )
    )
    if job is None:
        raise HTTPException(404, "Agent job not found")
    if job.actor_id != access.user_id:
        access.require(REVIEWERS)
    if job.state != "succeeded":
        raise HTTPException(409, "Agent review is unavailable")
    request = db.get(AgentRequest, agent_job_id)
    if request is None:
        raise HTTPException(409, "Agent review is unavailable")
    context = load_context(db, job, request, access.user_id, fresh=True)
    existing = db.scalar(select(Draft).where(Draft.agent_job_id == job.id))
    if existing is not None:
        raise HTTPException(409, "A draft already exists for this job")
    runs = dict(
        db.execute(
            select(AgentRun.role, AgentRun.output).where(
                AgentRun.job_id == job.id, AgentRun.status == "succeeded"
            )
        )
        .tuples()
        .all()
    )
    audited = AuditOutput.model_validate(runs["evidence_auditor"])
    rubric = RubricProposal.model_validate(runs["readiness_coach"])
    if not audited.claims:
        raise HTTPException(409, "No claims are available for review")
    inputs = AgentInput.model_validate(request.input)
    draft = Draft(
        project_id=access.project.id,
        agent_job_id=job.id,
        created_by=access.user_id,
        task=inputs.task,
        audience=[str(i) for i in inputs.audience],
        unresolved=audited.unresolved,
        proposed_rubric=rubric.model_dump(mode="json"),
    )
    db.add(draft)
    db.flush()
    ids: dict[str, UUID] = {}
    context_ids = tuple(UUID(i) for i in request.revision_ids)
    for position, item in enumerate(audited.claims):
        claim = Claim(project_id=access.project.id, created_by=access.user_id)
        db.add(claim)
        db.flush()
        add_revision(db, access, claim, item.content, context_ids=context_ids)
        db.add(
            DraftClaim(
                draft_id=draft.id,
                claim_id=claim.id,
                position=position,
                flags=item.flags,
            )
        )
        ids[item.key] = claim.id
    for origin, target, relation in {
        (ids[link.origin], ids[link.target], link.relation)
        for link in audited.relationships
    }:
        db.add(ClaimRelationship(origin_id=origin, target_id=target, relation=relation))
    audit(
        db, access.user_id, "draft.created", project=access.project, target_id=draft.id
    )
    result = draft_view(db, draft, context)
    db.commit()
    return result


def patch_claim(
    db: Session, user_id: UUID, claim_id: UUID, body: ClaimPatch
) -> ClaimPatchView:
    draft, access, _ = read_draft(db, body.draft_id, user_id, lock=True)
    access.require(REVIEWERS)
    if draft.revision != body.expected_revision:
        raise HTTPException(409, "Draft revision changed")
    link = db.get(DraftClaim, (draft.id, claim_id))
    claim = db.get(Claim, claim_id)
    if link is None or claim is None:
        raise HTTPException(404, "Claim not found")
    current_claim(db, access, claim_id)
    _, request, _ = draft_context(db, draft, user_id, fresh=True)
    allowed = set(request.revision_ids)
    if any(str(item.revision_id) not in allowed for item in body.content.evidence):
        raise HTTPException(422, "Evidence is outside the draft snapshot")
    claim.current_number += 1
    draft.revision += 1
    revision = add_revision(
        db,
        access,
        claim,
        body.content,
        reviewer_note=body.reason,
        context_ids=tuple(UUID(i) for i in request.revision_ids),
    )
    relations = {item.relation for item in body.content.evidence}
    flags = ["semantic_review_required"]
    if "supports" not in relations and body.content.status != "rejected":
        flags.append("supporting_evidence_missing")
        if "invalid_or_ambiguous_citation" in link.flags:
            flags.append("invalid_or_ambiguous_citation")
    if "contradicts" in relations:
        flags.append("contradictory_evidence")
    link.flags = flags
    audit(db, user_id, "claim.reviewed", project=access.project, target_id=claim.id)
    result = ClaimPatchView(draft_revision=draft.revision, claim=summary(revision))
    db.commit()
    return result
