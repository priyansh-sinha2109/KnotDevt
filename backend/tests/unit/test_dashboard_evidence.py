from uuid import uuid4

from app.agents.auditor import audit
from app.agents.dashboard import dashboard_summary
from app.schemas.agents import (
    Candidate,
    Citation,
    ContextBundle,
    ContextItem,
    DecisionOutput,
    WorkOutput,
)


def test_dashboard_status_is_not_a_human_decision() -> None:
    lines = [
        "GitHub Issue #2119 is an automatically generated Renovate Dependency "
        "Dashboard for WALA.",
        "Several dependency updates are awaiting status checks, including r8 v9.5.29.",
        "Open update pull requests include #2152 and #2153.",
        "The Eclipse JDT dependency update is blocked by a previously closed "
        "pull request #2121.",
    ]
    source = ContextItem(
        revision_id=uuid4(),
        source_id="WALA-2119",
        event_type="task",
        excerpt=" ".join(lines),
        event_time="2026-11-10T00:00:00Z",
        related_ids=[],
    )

    def citation(quote: str) -> Citation:
        return Citation(revision_id=source.revision_id, quote=quote)

    result = audit(
        ContextBundle(task="Understand dependency maintenance", evidence=[source]),
        DecisionOutput(
            claims=[
                Candidate(
                    key="pending",
                    kind="decision",
                    status="proposed",
                    statement=lines[1],
                    citations=[citation(lines[1])],
                ),
                Candidate(
                    key="open_pr",
                    kind="decision",
                    status="accepted",
                    statement=lines[2],
                    citations=[citation(lines[2])],
                ),
                Candidate(
                    key="closed_pr",
                    kind="decision",
                    status="accepted",
                    statement=lines[3],
                    citations=[citation(lines[3])],
                ),
            ],
            missing_rationale=[],
            relationships=[],
        ),
        WorkOutput(
            claims=[
                Candidate(
                    key="blocker",
                    kind="blocker",
                    status="unresolved",
                    statement=lines[3],
                    citations=[citation(lines[3])],
                ),
                Candidate(
                    key="owner",
                    kind="owner",
                    status="confirmed",
                    statement="No owner was assigned.",
                    citations=[citation(lines[0])],
                ),
                Candidate(
                    key="contact",
                    kind="contact",
                    status="confirmed",
                    statement="Contact the repository maintainers.",
                    citations=[citation(lines[0])],
                ),
                Candidate(
                    key="monitor",
                    kind="risk",
                    status="open",
                    statement="The checks are unmonitored.",
                    citations=[citation(lines[1])],
                ),
            ],
            recurring_problem_candidates=[],
            relationships=[],
        ),
    )
    claims = [item.content for item in result.claims]
    assert [item.kind for item in claims] == [
        "overview",
        "work_item",
        "work_item",
        "blocker",
    ]
    assert [item.status for item in claims] == [
        "confirmed",
        "open",
        "open",
        "unresolved",
    ]
    assert any(
        "does not identify a confirmed human owner" in note
        for note in result.unresolved
    )
    for claim in claims:
        assert len(claim.evidence) == 1
        span = claim.evidence[0]
        assert span.quote == source.excerpt[span.start : span.end] == claim.statement
    mixed = source.model_copy(
        update={"excerpt": source.excerpt + " The release team approved migration."}
    )
    assert (
        dashboard_summary(ContextBundle(task="Review migration", evidence=[mixed]))
        is None
    )


def test_exact_span_and_semantic_review_are_separate() -> None:
    source = ContextItem(
        revision_id=uuid4(),
        source_id="task",
        event_type="task",
        excerpt="Testing is pending. Testing is pending. A release date is unknown.",
        event_time="2026-11-10T00:00:00Z",
        related_ids=[],
    )
    output = audit(
        ContextBundle(task="Review release", evidence=[source]),
        DecisionOutput(claims=[], missing_rationale=[], relationships=[]),
        WorkOutput(
            claims=[
                Candidate(
                    key="wrong_meaning",
                    kind="work_item",
                    status="open",
                    statement="Nobody is monitoring the release.",
                    citations=[
                        Citation(
                            revision_id=source.revision_id,
                            quote="A release date is unknown.",
                        )
                    ],
                ),
                Candidate(
                    key="ambiguous",
                    kind="work_item",
                    status="open",
                    statement="Testing is pending.",
                    citations=[
                        Citation(
                            revision_id=source.revision_id, quote="Testing is pending."
                        )
                    ],
                ),
            ],
            recurring_problem_candidates=[],
            relationships=[],
        ),
    )
    valid, ambiguous = output.claims
    assert valid.content.evidence and "semantic_review_required" in valid.flags
    assert not ambiguous.content.evidence
    assert ambiguous.content.status == "unverified"
    assert "invalid_or_ambiguous_citation" in ambiguous.flags
    assert "supporting_evidence_missing" in ambiguous.flags


def test_dashboard_adapter_is_identifier_independent_and_order_tolerant() -> None:
    sentences = [
        "GitHub Issue #9042 is an automatically generated Renovate Dependency "
        "Dashboard for Acme-Widget.",
        "Several dependency updates are awaiting status checks, including "
        "lunar-sdk v8.1.",
        "Open update pull requests include #77 and #81.",
        "The Quartz Engine update is blocked by a previously closed pull request #63.",
    ]
    item = ContextItem(
        revision_id=uuid4(),
        source_id="different-repository-9042",
        event_type="task",
        excerpt=" ".join([sentences[0], sentences[3], sentences[1], sentences[2]]),
        event_time="2026-11-10T00:00:00Z",
        related_ids=[],
    )
    result = dashboard_summary(ContextBundle(task="Review updates", evidence=[item]))
    assert result is not None
    assert [claim.content.kind for claim in result.claims] == [
        "overview",
        "work_item",
        "work_item",
        "blocker",
    ]
    assert all(
        claim.content.evidence[0].revision_id == item.revision_id
        for claim in result.claims
    )


def test_dashboard_adapter_falls_back_for_multiple_or_missing_sources() -> None:
    item = ContextItem(
        revision_id=uuid4(),
        source_id="dashboard",
        event_type="task",
        excerpt=(
            "GitHub Issue #1 is an automatically generated Renovate Dependency "
            "Dashboard for Demo. Several dependency updates are awaiting status "
            "checks, including alpha v2. "
            "Open update pull requests include #2 and #3."
        ),
        event_time="2026-11-10T00:00:00Z",
        related_ids=[],
    )
    assert dashboard_summary(ContextBundle(task="Review", evidence=[item])) is None
    second = item.model_copy(update={"revision_id": uuid4(), "source_id": "context"})
    assert (
        dashboard_summary(ContextBundle(task="Review", evidence=[item, second])) is None
    )
