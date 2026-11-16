from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.agents import ContextItem, RubricProposal, ShortText
from app.schemas.critical_gaps import CriticalGapReview
from app.schemas.evidence import ClaimContent, ClaimSummary
from app.schemas.sources import StrictModel

VersionState = Literal["approved", "stale", "unavailable", "withdrawn"]


class DraftInput(StrictModel):
    agent_job_id: UUID


class SourceDraftInput(StrictModel):
    task: ShortText
    audience: Annotated[list[UUID], Field(min_length=1, max_length=8)]
    source_ids: list[str] = Field(default_factory=list, max_length=16)


class DraftClaimView(BaseModel):
    claim: ClaimSummary
    flags: list[str]
    reviewer_note: str | None


class DraftView(BaseModel):
    id: UUID
    project_id: UUID
    agent_job_id: UUID
    revision: int
    task: str
    mode: Literal["ai_assisted", "source_based"]
    audience: list[UUID]
    source_revision_ids: list[UUID]
    source_snapshot: list[ContextItem]
    claims: list[DraftClaimView]
    proposed_rubric: RubricProposal
    unresolved: list[str]


class ClaimPatch(StrictModel):
    draft_id: UUID
    expected_revision: Annotated[int, Field(ge=1)]
    content: ClaimContent
    reason: ShortText


class ClaimPatchView(BaseModel):
    draft_revision: int
    claim: ClaimSummary


class ApprovalInput(StrictModel):
    expected_revision: Annotated[int, Field(ge=1)]
    rubric: RubricProposal
    critical_gap_review: CriticalGapReview | None = None


class VersionContent(BaseModel):
    project_id: UUID
    draft_id: UUID
    number: int
    task: str
    content_hash: str
    approved_by: UUID
    approved_at: datetime
    claims: list[ClaimSummary]
    rubric_id: UUID
    source_revision_ids: list[UUID]
    unresolved: list[str]


class VersionView(BaseModel):
    id: UUID
    status: VersionState
    handover: VersionContent | None = None
