from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.schemas.evidence import ClaimContent, ClaimKind, ClaimStatus, Relation
from app.schemas.sources import SourceKey, StrictModel

Stage = Literal[
    "context_collector",
    "decision_analyst",
    "work_mapper",
    "evidence_auditor",
    "readiness_coach",
]
ShortText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]
CandidateKey = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,39}$")]


class AgentInput(StrictModel):
    task: ShortText
    audience: Annotated[list[UUID], Field(min_length=1, max_length=8)]
    source_ids: Annotated[list[SourceKey], Field(max_length=16)] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def unique(self) -> "AgentInput":
        if len(set(self.audience)) != len(self.audience):
            raise ValueError("Duplicate audience member")
        return self


class ContextItem(StrictModel):
    revision_id: UUID
    source_id: str
    event_type: str
    excerpt: str
    event_time: str
    related_ids: list[str]


class ContextBundle(StrictModel):
    task: ShortText
    evidence: Annotated[list[ContextItem], Field(min_length=1, max_length=16)]
    unresolved_ids: list[str] = Field(default_factory=list)


class Citation(StrictModel):
    revision_id: UUID
    quote: Annotated[str, StringConstraints(min_length=1, max_length=1600)]
    relation: Relation = "supports"
    start: Annotated[int, Field(ge=0, le=12000)] | None = None
    end: Annotated[int, Field(ge=1, le=12000)] | None = None
    prefix: Annotated[str, StringConstraints(max_length=240)] | None = None
    suffix: Annotated[str, StringConstraints(max_length=240)] | None = None

    @model_validator(mode="after")
    def valid_location(self) -> "Citation":
        if (self.start is None) != (self.end is None):
            raise ValueError("Citation start and end must be supplied together")
        if self.start is not None and self.end is not None:
            if self.end <= self.start or self.end - self.start != len(self.quote):
                raise ValueError("Citation offsets do not match the quote length")
        return self


class Candidate(StrictModel):
    key: CandidateKey
    kind: ClaimKind
    status: ClaimStatus
    statement: ShortText
    citations: Annotated[list[Citation], Field(max_length=6)]


class CandidateLink(StrictModel):
    origin: CandidateKey
    target: CandidateKey
    relation: Relation


class DecisionOutput(StrictModel):
    claims: Annotated[list[Candidate], Field(max_length=8)]
    missing_rationale: Annotated[list[ShortText], Field(max_length=8)]
    relationships: Annotated[list[CandidateLink], Field(max_length=12)]


class WorkOutput(StrictModel):
    claims: Annotated[list[Candidate], Field(max_length=12)]
    recurring_problem_candidates: Annotated[list[ShortText], Field(max_length=8)]
    relationships: Annotated[list[CandidateLink], Field(max_length=12)]


class AuditedClaim(StrictModel):
    key: CandidateKey
    content: ClaimContent
    flags: list[str]


class AuditOutput(StrictModel):
    claims: list[AuditedClaim]
    relationships: list[CandidateLink]
    unresolved: list[str]


Dimension = Literal["action", "prerequisites", "evidence", "escalation"]


class Question(StrictModel):
    dimension: Dimension
    prompt: ShortText
    choices: Annotated[list[ShortText], Field(min_length=2, max_length=5)]
    correct_choice: Annotated[int, Field(ge=0, le=4)]
    weight: Annotated[int, Field(ge=1, le=100)]
    explanation: ShortText
    evidence_revision_ids: Annotated[list[UUID], Field(min_length=1, max_length=6)]

    @model_validator(mode="after")
    def valid_options(self) -> "Question":
        if self.correct_choice >= len(self.choices) or len(set(self.choices)) != len(
            self.choices
        ):
            raise ValueError("Invalid question choices")
        return self


class RubricProposal(StrictModel):
    title: ShortText
    threshold: Annotated[int, Field(ge=1, le=100)] = 80
    questions: Annotated[list[Question], Field(min_length=4, max_length=4)]

    @model_validator(mode="after")
    def valid_weights(self) -> "RubricProposal":
        if len({item.dimension for item in self.questions}) != 4:
            raise ValueError("Every readiness dimension must appear once")
        if sum(item.weight for item in self.questions) != 100:
            raise ValueError("Rubric weights must sum to 100")
        return self


class CoachInput(StrictModel):
    context: ContextBundle
    audit: AuditOutput


RunOutput = ContextBundle | DecisionOutput | WorkOutput | AuditOutput | RubricProposal


class RunView(BaseModel):
    id: UUID
    role: Stage
    attempt: int
    model: str
    prompt_version: str
    status: Literal["running", "succeeded", "failed"]
    timeout_seconds: int
    attempt_limit: int
    tools: list[str]
    output: RunOutput | None
    error_code: str | None
