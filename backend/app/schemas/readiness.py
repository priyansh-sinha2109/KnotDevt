from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints, field_validator

from app.schemas.agents import Dimension, ShortText
from app.schemas.sources import StrictModel

PackageStatus = Literal[
    "ready",
    "blocked_by_project_gap",
    "access_review_required",
    "stale_or_requires_review",
]
RecipientStatus = Literal[
    "ready_for_scoped_task",
    "needs_guided_practice",
    "blocked_by_project_gap",
    "access_review_required",
    "stale_or_requires_review",
]
Gate = Literal[
    "critical_prerequisite",
    "required_access",
    "task_not_approved",
    "stale_evidence",
    "critical_gap_review_required",
]


class PackageReadiness(BaseModel):
    status: PackageStatus
    gates: list[Gate]


class RehearsalQuestion(BaseModel):
    dimension: Dimension
    prompt: str
    choices: list[str]
    weight: int


class Rehearsal(BaseModel):
    id: UUID
    version_id: UUID
    package: PackageReadiness
    title: str | None = None
    threshold: int | None = None
    questions: list[RehearsalQuestion] = Field(default_factory=list)


class AttemptInput(StrictModel):
    answers: Annotated[
        dict[Dimension, Annotated[int, Field(ge=0, le=4, strict=True)]],
        Field(max_length=4),
    ]
    explanation: (
        Annotated[
            str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
        ]
        | None
    ) = None
    client_attempt_id: UUID | None = None

    @field_validator("explanation")
    @classmethod
    def validate_text(cls, value: str | None) -> str | None:
        if value is not None and "\x00" in value:
            raise ValueError("Invalid explanation")
        return value


class ScoreFeedback(BaseModel):
    dimension: Dimension
    points: int
    weight: int
    explanation: str


class Advice(BaseModel):
    status: Literal["queued", "succeeded", "failed"]
    model: str
    prompt_version: str
    feedback: str | None


class ReviewInput(StrictModel):
    feedback: ShortText


class ReviewView(BaseModel):
    reviewer_id: UUID
    feedback: str
    reviewed_at: datetime


class Assessment(BaseModel):
    id: UUID
    version_id: UUID
    rubric_id: UUID
    recipient_id: UUID
    attempted_at: datetime
    status: RecipientStatus
    package: PackageReadiness
    assessed_status: RecipientStatus | None = None
    score: int | None = None
    answers: dict[str, int] = Field(default_factory=dict)
    explanation: str | None = None
    feedback: list[ScoreFeedback] = Field(default_factory=list)
    advisory: Advice | None = None
    review: ReviewView | None = None
    review_status: Literal["pending", "reviewed", "withheld"]
