from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    field_validator,
    model_validator,
)

SourceKey = Annotated[
    str, StringConstraints(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$")
]
Provider = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_-]{0,63}$")]
Kind = Literal["issue-events", "conversation-notes"]
Policy = Literal["project", "restricted"]
JobState = Literal["queued", "succeeded", "failed"]
JobPhase = Literal[
    "queued",
    "waiting_retry",
    "awaiting_human_review",
    "succeeded",
    "failed",
]
JobNextAction = Literal["wait", "review", "inspect_error", "none"]
MAX_IMPORT_BYTES = 1024 * 1024


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceEntry(StrictModel):
    source_id: SourceKey
    author: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)
    ]
    event_at: AwareDatetime
    reference: Annotated[
        str, StringConstraints(max_length=1024, pattern=r"^(https://|fixture:)[^\s]+$")
    ]
    text: Annotated[str, StringConstraints(min_length=1, max_length=12000)]
    related_ids: Annotated[list[SourceKey], Field(max_length=20)] = Field(
        default_factory=list
    )
    access: Policy = "project"

    @field_validator("event_at")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @field_validator("text", "author", "reference")
    @classmethod
    def postgres_text(cls, value: str) -> str:
        if "\x00" in value or not value.strip():
            raise ValueError("Invalid text")
        return value


class IssueEvent(SourceEntry):
    event_type: Literal["proposal", "implementation", "task", "comment"]


class ConversationNote(SourceEntry):
    event_type: Literal["decision", "meeting", "message"]


class IssueImport(StrictModel):
    kind: Literal["issue-events"]
    provider: Provider
    events: Annotated[list[IssueEvent], Field(min_length=1, max_length=100)]

    @model_validator(mode="after")
    def unique_ids(self) -> "IssueImport":
        if len({item.source_id for item in self.events}) != len(self.events):
            raise ValueError("Duplicate source ID in import")
        return self


class ConversationImport(StrictModel):
    kind: Literal["conversation-notes"]
    provider: Provider
    notes: Annotated[list[ConversationNote], Field(min_length=1, max_length=100)]

    @model_validator(mode="after")
    def unique_ids(self) -> "ConversationImport":
        if len({item.source_id for item in self.notes}) != len(self.notes):
            raise ValueError("Duplicate source ID in import")
        return self


ImportInput = Annotated[IssueImport | ConversationImport, Field(discriminator="kind")]
IMPORT_INPUT: TypeAdapter[ImportInput] = TypeAdapter(ImportInput)  # type: ignore[arg-type]


def import_schema() -> dict[str, Any]:
    schema = IMPORT_INPUT.json_schema()
    definitions = schema.pop("$defs")
    schema.pop("discriminator", None)

    def inline(value: Any) -> Any:
        if isinstance(value, dict):
            if "$ref" in value:
                return inline(definitions[value["$ref"].rsplit("/", 1)[-1]])
            return {key: inline(child) for key, child in value.items()}
        if isinstance(value, list):
            return [inline(child) for child in value]
        return value

    return {key: inline(value) for key, value in schema.items()}


class ImportedRevision(BaseModel):
    source_id: UUID
    revision_id: UUID
    duplicate: bool


class JobView(BaseModel):
    id: UUID
    project_id: UUID
    kind: str
    state: JobState
    phase: JobPhase
    next_action: JobNextAction
    attempt_count: int
    next_retry_at: datetime | None
    created_at: datetime
    error_code: str | None
    revisions: list[ImportedRevision] = Field(default_factory=list)


class SourceView(BaseModel):
    id: UUID
    revision_id: UUID
    original_id: str
    provider: str
    kind: str
    event_type: str
    policy: Policy
    content_hash: str
    author: str
    reference: str
    excerpt: str
    event_at: datetime
    imported_at: datetime


class SourcesPage(BaseModel):
    items: list[SourceView]
    next_offset: int | None


class SourcePolicy(StrictModel):
    policy: Policy
    allowed_users: Annotated[set[UUID], Field(max_length=100)] = Field(
        default_factory=set
    )

    @model_validator(mode="after")
    def project_has_no_acl(self) -> "SourcePolicy":
        if self.policy == "project" and self.allowed_users:
            raise ValueError("Project-visible sources cannot have an allowlist")
        return self
