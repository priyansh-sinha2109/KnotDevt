from uuid import uuid4

import pytest

from app.agents.auditor import audit
from app.schemas.agents import (
    Candidate,
    Citation,
    ContextBundle,
    ContextItem,
    DecisionOutput,
    WorkOutput,
)


def snapshot(
    *,
    repository: str,
    number: int,
    state: str,
    assignees: str,
    body: str,
) -> ContextItem:
    excerpt = (
        f"GitHub issue {repository}#{number}\n"
        "Title: Unrelated issue\n"
        f"State at snapshot: {state}\n"
        "Author: reporter\n"
        f"Assignees: {assignees}\n"
        "Created: 2026-01-01T00:00:00Z\n"
        "Updated: 2026-01-02T00:00:00Z\n"
        f"Closed: {'2026-01-02T00:00:00Z' if state == 'closed' else 'Not closed'}\n\n"
        f"{body}"
    )
    return ContextItem(
        revision_id=uuid4(),
        source_id=f"snapshot-{number}",
        event_type="task",
        excerpt=excerpt,
        event_time="2026-01-02T00:00:00Z",
        related_ids=[],
    )


def run(item: ContextItem, candidate: Candidate | None = None):
    return audit(
        ContextBundle(task="Review issue", evidence=[item]),
        DecisionOutput(claims=[], missing_rationale=[], relationships=[]),
        WorkOutput(
            claims=[candidate] if candidate else [],
            recurring_problem_candidates=[],
            relationships=[],
        ),
    )


@pytest.mark.parametrize(
    "repository,number,assignee",
    [("alpha/tool", 17, "dev-a"), ("beta/library", 902, "maintainer_b")],
)
def test_snapshot_state_and_explicit_assignee_are_preserved(
    repository: str, number: int, assignee: str
) -> None:
    item = snapshot(
        repository=repository,
        number=number,
        state="closed",
        assignees=assignee,
        body="The report describes a historical bug.",
    )
    result = run(item)
    assert [(claim.content.kind, claim.content.status) for claim in result.claims] == [
        ("overview", "confirmed"),
        ("owner", "confirmed"),
    ]
    assert assignee in result.claims[1].content.statement
    assert all(claim.content.evidence for claim in result.claims)
    assert any("closure alone" in note for note in result.unresolved)


def test_closed_issue_downgrades_open_work_without_completion_or_ongoing_evidence() -> (
    None
):
    item = snapshot(
        repository="example/project",
        number=55,
        state="closed",
        assignees="casey",
        body="Calling fill returns a view of the original array.",
    )
    quote = "Calling fill returns a view of the original array."
    start = item.excerpt.index(quote)
    result = run(
        item,
        Candidate(
            key="work_bug",
            kind="work_item",
            status="open",
            statement="Fix the fill view bug.",
            citations=[
                Citation(
                    revision_id=item.revision_id,
                    quote=quote,
                    start=start,
                    end=start + len(quote),
                )
            ],
        ),
    )
    work = result.claims[0]
    assert work.content.status == "unverified"
    assert "closed_snapshot_open_status_unverified" in work.flags
    assert result.claims[1].content.statement.endswith("closed.")


def test_closed_snapshot_with_explicit_ongoing_blocker_preserves_open_status() -> None:
    item = snapshot(
        repository="other/tool",
        number=8,
        state="closed",
        assignees="owner-x",
        body="The migration remains blocked pending vendor approval.",
    )
    quote = "The migration remains blocked pending vendor approval."
    start = item.excerpt.index(quote)
    result = run(
        item,
        Candidate(
            key="work_blocked",
            kind="blocker",
            status="open",
            statement=quote,
            citations=[
                Citation(
                    revision_id=item.revision_id,
                    quote=quote,
                    start=start,
                    end=start + len(quote),
                )
            ],
        ),
    )
    assert result.claims[0].content.status == "open"


def test_missing_assignee_is_uncertainty_not_confirmed_absence() -> None:
    item = snapshot(
        repository="missing/owner",
        number=4,
        state="open",
        assignees="None listed",
        body="A feature request is awaiting review.",
    )
    result = run(item)
    assert not any(claim.content.kind == "owner" for claim in result.claims)
    assert any("does not prove" in note for note in result.unresolved)
