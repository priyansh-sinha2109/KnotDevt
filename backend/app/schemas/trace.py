from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.evidence import ClaimSummary, EvidenceView, Relation
from app.schemas.handover import VersionState


class TraceEdge(BaseModel):
    origin_id: UUID
    target_id: UUID
    relation: Relation


class TraceClaim(BaseModel):
    claim: ClaimSummary
    evidence: list[EvidenceView]


class ContextTrace(BaseModel):
    version_id: UUID | None = None
    status: Literal["current"] | VersionState
    selected: TraceClaim | None = None
    timeline: list[TraceClaim] = Field(default_factory=list)
    relationships: list[TraceEdge] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)
    outline: list[str] = Field(default_factory=list)
