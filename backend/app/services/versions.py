import hashlib
import json
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.evidence import Claim, ClaimRevision, EvidenceLink
from app.db.handover import Rubric, Version, VersionClaim, VersionWithdrawal
from app.db.identity import Role
from app.db.sources import Job, Source, SourceRevision
from app.repositories.handover import draft_claims, version_claims
from app.repositories.sources import can_read_source, current_revision_id, lock_project
from app.schemas.handover import (
    ApprovalInput,
    VersionContent,
    VersionState,
    VersionView,
)
from app.services.access import REVIEWERS, ProjectAccess, audit, require_project
from app.services.agents import load_context
from app.services.critical_gaps import stored_gap_review, validate_gap_review
from app.services.drafts import draft_context, read_draft
from app.services.evidence import summary


def approve(
    db: Session, draft_id: UUID, user_id: UUID, body: ApprovalInput
) -> VersionView:
    draft, access = read_draft(db, draft_id, user_id, lock=True)
    access.require(REVIEWERS)
    if draft.revision != body.expected_revision:
        raise HTTPException(409, "Draft revision changed")
    job, request = draft_context(db, draft, user_id, fresh=True)
    for member in draft.audience:
        recipient_id = UUID(member)
        recipient = require_project(db, draft.project_id, recipient_id)
        if recipient.role != Role.RECIPIENT:
            raise HTTPException(409, "Audience must be assigned project recipients")
        load_context(db, job, request, recipient_id, fresh=True)
    if any(
        set(str(i) for i in item.evidence_revision_ids) - set(request.revision_ids)
        for item in body.rubric.questions
    ):
        raise HTTPException(
            422, "Rubric references evidence outside the draft snapshot"
        )

    claims = draft_claims(db, draft.id)
    revisions = [claim for claim, _ in claims if claim.status != "rejected"]
    if not revisions:
        raise HTTPException(409, "No claims remain for approval")
    for revision in revisions:
        if revision.status in {"unverified", "unresolved"}:
            continue
        support = db.scalar(
            select(EvidenceLink.id)
            .where(
                EvidenceLink.claim_revision_id == revision.id,
                EvidenceLink.relation == "supports",
            )
            .limit(1)
        )
        if support is None:
            raise HTTPException(409, "A factual claim has no supporting evidence")

    rubric = body.rubric.model_dump(mode="json")
    if body.critical_gap_review is not None:
        review = body.critical_gap_review
        validate_gap_review(db, review, claims, request.revision_ids)
        # Normalize unordered review inputs before hashing the approval.
        normalized = review.model_dump(mode="json")
        normalized["reviewed_source_revision_ids"] = sorted(
            normalized["reviewed_source_revision_ids"]
        )
        normalized["claims"].sort(key=lambda item: item["claim_revision_id"])
        rubric["critical_gap_review"] = normalized
    snapshot = {
        "task": draft.task,
        "audience": draft.audience,
        "unresolved": draft.unresolved,
        "claim_revisions": [str(item.id) for item in revisions],
        "sources": request.revision_ids,
        "policy": request.policy_revisions,
        "rubric": rubric,
    }
    digest = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
    if (
        db.scalar(
            select(Version.id).where(
                Version.draft_id == draft.id,
                Version.content_hash == digest,
            )
        )
        is not None
    ):
        raise HTTPException(409, "Exact content is already approved")
    number = (
        db.scalar(select(func.max(Version.number)).where(Version.draft_id == draft.id))
        or 0
    ) + 1

    resume = Job(
        project_id=draft.project_id,
        actor_id=user_id,
        kind="review_resume",
        input_hash=digest,
    )
    db.add(resume)
    db.flush()
    version = Version(
        project_id=draft.project_id,
        draft_id=draft.id,
        resume_job_id=resume.id,
        number=number,
        draft_revision=draft.revision,
        approved_by=user_id,
        content_hash=digest,
        task=draft.task,
        audience=draft.audience,
        unresolved=draft.unresolved,
        source_revision_ids=request.revision_ids,
        source_policy_revisions=request.policy_revisions,
    )
    db.add(version)
    db.flush()
    db.add(Rubric(version_id=version.id, spec=rubric))
    db.add_all(
        VersionClaim(version_id=version.id, claim_revision_id=item.id, position=index)
        for index, item in enumerate(revisions)
    )
    draft.revision += 1
    audit(
        db, user_id, "handover.approved", project=access.project, target_id=version.id
    )
    result = version_view(db, version, access)
    db.commit()
    return result


def version_access(
    db: Session,
    version_id: UUID,
    user_id: UUID,
    *,
    assigned_only: bool = False,
) -> tuple[Version, ProjectAccess]:
    version = db.get(Version, version_id)
    if version is None:
        raise HTTPException(404, "Handover version not found")
    try:
        access = require_project(db, version.project_id, user_id)
    except HTTPException:
        raise HTTPException(404, "Handover version not found") from None
    assigned = str(user_id) in version.audience and access.role == Role.RECIPIENT
    if not assigned and (assigned_only or access.role not in REVIEWERS):
        raise HTTPException(404, "Handover version not found")
    return version, access


def version_state(db: Session, version: Version, user_id: UUID) -> VersionState:
    if db.get(VersionWithdrawal, version.id) is not None:
        return "withdrawn"
    stale = (
        db.scalar(
            select(Version.id)
            .where(
                Version.draft_id == version.draft_id,
                Version.number > version.number,
            )
            .limit(1)
        )
        is not None
    )
    revisions = db.execute(
        select(
            Source.id, Source.policy_revision, SourceRevision.id, current_revision_id()
        )
        .join(SourceRevision, SourceRevision.source_id == Source.id)
        .where(
            Source.project_id == version.project_id,
            can_read_source(user_id),
            SourceRevision.id.in_(
                [UUID(value) for value in version.source_revision_ids]
            ),
        )
    ).all()
    if len(revisions) != len(version.source_revision_ids):
        return "unavailable"
    if any(
        policy != version.source_policy_revisions[str(source_id)]
        or latest != revision_id
        for source_id, policy, revision_id, latest in revisions
    ):
        stale = True
    if not stale:
        review = stored_gap_review(db, version.id)
        reviewed = [item.claim_revision_id for item in review.claims] if review else []
        critical = select(VersionClaim.claim_revision_id).where(
            VersionClaim.version_id == version.id
        )
        stale = (
            db.scalar(
                select(ClaimRevision.id)
                .join(Claim, Claim.id == ClaimRevision.claim_id)
                .where(
                    Claim.project_id == version.project_id,
                    Claim.current_number != ClaimRevision.number,
                    or_(
                        ClaimRevision.id.in_(reviewed),
                        ClaimRevision.id.in_(critical)
                        & ClaimRevision.kind.in_(("prerequisite", "blocker")),
                    ),
                )
                .limit(1)
            )
            is not None
        )
    return "stale" if stale else "approved"


def version_view(db: Session, version: Version, access: ProjectAccess) -> VersionView:
    state = version_state(db, version, access.user_id)
    if state in {"unavailable", "withdrawn"}:
        return VersionView(id=version.id, status=state)
    rubric_id = db.scalars(
        select(Rubric.id).where(Rubric.version_id == version.id)
    ).one()
    return VersionView(
        id=version.id,
        status=state,
        handover=VersionContent(
            project_id=version.project_id,
            draft_id=version.draft_id,
            number=version.number,
            task=version.task,
            content_hash=version.content_hash,
            approved_by=version.approved_by,
            approved_at=version.approved_at,
            claims=[summary(row) for row in version_claims(db, version.id)],
            rubric_id=rubric_id,
            source_revision_ids=[UUID(i) for i in version.source_revision_ids],
            unresolved=version.unresolved,
        ),
    )


def withdraw(db: Session, version_id: UUID, user_id: UUID) -> None:
    version, access = version_access(db, version_id, user_id)
    access.require(REVIEWERS)
    lock_project(db, version.project_id)
    require_project(db, version.project_id, user_id).require(REVIEWERS)
    if db.get(VersionWithdrawal, version.id) is not None:
        return
    db.add(VersionWithdrawal(version_id=version.id, actor_id=user_id))
    audit(
        db, user_id, "handover.withdrawn", project=access.project, target_id=version.id
    )
    db.commit()
