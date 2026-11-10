import re
from dataclasses import dataclass

from app.schemas.agents import ContextItem

HEADER = re.compile(r"^GitHub issue ([^\s#]+/[^\s#]+)#([1-9][0-9]*)$")
FIELD = re.compile(
    r"^(Title|State at snapshot|Author|Assignees|Created|Updated|Closed): (.+)$"
)


@dataclass(frozen=True)
class SnapshotMetadata:
    state: str
    state_start: int
    state_quote: str
    assignees: tuple[str, ...]
    assignee_start: int
    assignee_quote: str


def github_snapshot(item: ContextItem) -> SnapshotMetadata | None:
    """Parse the bounded, explicit public-snapshot envelope used by imports."""
    raw_lines = item.excerpt.splitlines(keepends=True)
    lines = [line.rstrip("\r\n") for line in raw_lines]
    if len(lines) < 8 or HEADER.fullmatch(lines[0]) is None:
        return None
    values: dict[str, tuple[str, str, int]] = {}
    cursor = len(raw_lines[0])
    for raw_line, line in zip(raw_lines[1:8], lines[1:8], strict=True):
        match = FIELD.fullmatch(line)
        if match is None:
            return None
        values[match[1]] = (match[2], line, cursor)
        cursor += len(raw_line)
    required = {
        "Title",
        "State at snapshot",
        "Author",
        "Assignees",
        "Created",
        "Updated",
        "Closed",
    }
    if set(values) != required:
        return None
    state, state_quote, state_start = values["State at snapshot"]
    raw_assignees, assignee_quote, assignee_start = values["Assignees"]
    assignees = (
        ()
        if raw_assignees.casefold() == "none listed"
        else tuple(value.strip() for value in raw_assignees.split(",") if value.strip())
    )
    return SnapshotMetadata(
        state=state.casefold(),
        state_start=state_start,
        state_quote=state_quote,
        assignees=assignees,
        assignee_start=assignee_start,
        assignee_quote=assignee_quote,
    )
