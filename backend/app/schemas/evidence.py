from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.schemas.sources import StrictModel

ClaimKind = Literal[
    "overview",
    "decision",
    "work_item",
    "owner",
    "contact",
    "prerequisite",
    "blocker",
    "risk",
    "next_action",
]
ClaimStatus = Literal[
    "unverified",
    "proposed",
    "accepted",
    "implemented",
    "conflicting",
    "open",
    "confirmed",
    "suggested",
    "unresolved",
    "resolved",
    "rejected",
]
Relation = Literal["supports", "contradicts", "supersedes", "requires"]
LinkKind = Literal["supports", "contradicts", "supersedes", "requires", "context"]


class EvidencePointer(StrictModel):
    revision_id: UUID
    start: Annotated[int, Field(ge=0, le=12000)]
    end: Annotated[int, Field(ge=1, le=12000)]
    quote: Annotated[str, StringConstraints(min_length=1, max_length=12000)]
    relation: Relation = "supports"

    @model_validator(mode="after")
    def valid_span(self) -> "EvidencePointer":
        if self.end - self.start != len(self.quote):
            raise ValueError("Span does not match quote length")
        return self


class ClaimLink(StrictModel):
    target_id: UUID
    relation: Relation


class ClaimContent(StrictModel):
    kind: ClaimKind
    status: ClaimStatus = "unverified"
    statement: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)
    ]
    evidence: Annotated[list[EvidencePointer], Field(max_length=24)] = Field(
        default_factory=list
    )

    @field_validator("statement")
    @classmethod
    def valid_statement(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("Invalid statement")
        return value

    @model_validator(mode="after")
    def provenance_required(self) -> "ClaimContent":
        if (
            self.status not in {"unverified", "unresolved", "rejected"}
            and not self.evidence
        ):
            raise ValueError("A factual claim requires evidence")
        return self


class ClaimInput(ClaimContent):
    relationships: Annotated[list[ClaimLink], Field(max_length=20)] = Field(
        default_factory=list
    )


class ClaimSummary(BaseModel):
    id: UUID
    revision_id: UUID
    number: int
    kind: ClaimKind
    status: ClaimStatus
    statement: str


class EvidenceView(BaseModel):
    source_id: UUID
    revision_id: UUID
    original_id: str
    provider: str
    event_type: str
    excerpt: str
    start: int
    end: int
    author: str
    event_at: datetime
    imported_at: datetime
    reference: str
    relation: LinkKind
    support: Literal["supporting", "contradicting", "related"]


class RelatedClaim(BaseModel):
    claim: ClaimSummary
    relation: Relation
    direction: Literal["incoming", "outgoing"]


class EvidenceBranch(BaseModel):
    evidence: EvidenceView | None = None
    related_claim: RelatedClaim | None = None


class EvidenceTree(BaseModel):
    root: ClaimSummary
    branches: list[EvidenceBranch]
    next_offset: int | None


class EvidenceOutline(BaseModel):
    claim: ClaimSummary
    lines: list[str]
    next_offset: int | None
