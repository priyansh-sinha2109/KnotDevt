from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.agents import ShortText
from app.schemas.sources import StrictModel

GapKind = Literal["prerequisite", "blocker", "approval", "ownership"]
Disposition = Literal["blocking", "unverified", "resolved", "non_blocking"]


class ClaimGapReview(StrictModel):
    claim_revision_id: UUID
    classification: GapKind | Literal["non_critical"]
    disposition: Disposition
    rationale: ShortText

    @model_validator(mode="after")
    def consistent_disposition(self) -> "ClaimGapReview":
        if (self.classification == "non_critical") != (
            self.disposition == "non_blocking"
        ):
            raise ValueError("Non-critical items require a non-blocking disposition")
        return self


class AdditionalGap(StrictModel):
    classification: GapKind
    disposition: Literal["blocking", "unverified"]
    source_revision_id: UUID
    rationale: ShortText


class CriticalGapReview(StrictModel):
    reviewed_source_revision_ids: Annotated[set[UUID], Field(max_length=16)]
    claims: Annotated[list[ClaimGapReview], Field(max_length=32)]
    additional_gaps: Annotated[list[AdditionalGap], Field(max_length=16)] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def unique_claim_revisions(self) -> "CriticalGapReview":
        if len({item.claim_revision_id for item in self.claims}) != len(self.claims):
            raise ValueError("Each claim revision requires one disposition")
        return self
