from uuid import uuid4

import pytest

from app.agents.auditor import audit
from app.agents.citations import resolve_citation
from app.agents.provider import normalize_citations
from app.schemas.agents import (
    Candidate,
    Citation,
    ContextBundle,
    ContextItem,
    DecisionOutput,
    WorkOutput,
)


def context(text: str) -> tuple[ContextBundle, ContextItem]:
    item = ContextItem(
        revision_id=uuid4(),
        source_id="unrelated-duplicate",
        event_type="task",
        excerpt=text,
        event_time="2026-11-10T00:00:00Z",
        related_ids=[],
    )
    return ContextBundle(task="Review duplicated evidence", evidence=[item]), item


def test_repeated_quote_requires_offsets_or_unique_context() -> None:
    text = "First context: repeated sentence. Other context: repeated sentence."
    _, item = context(text)
    ambiguous = Citation(revision_id=item.revision_id, quote="repeated sentence.")
    assert resolve_citation(text, ambiguous) is None

    second = text.rindex("repeated sentence.")
    located = Citation(
        revision_id=item.revision_id,
        quote="repeated sentence.",
        start=second,
        end=second + len("repeated sentence."),
    )
    assert resolve_citation(text, located).start == second  # type: ignore[union-attr]

    contextual = Citation(
        revision_id=item.revision_id,
        quote="repeated sentence.",
        prefix="Other context: ",
    )
    assert resolve_citation(text, contextual).start == second  # type: ignore[union-attr]


def test_wrong_offset_never_selects_between_repeated_occurrences() -> None:
    text = "same quote. separator same quote."
    _, item = context(text)
    wrong = Citation(
        revision_id=item.revision_id,
        quote="same quote.",
        start=1,
        end=1 + len("same quote."),
    )
    assert resolve_citation(text, wrong) is None


def test_provider_normalizes_unique_quote_and_rejects_ambiguous_quote() -> None:
    bundle, item = context("Unique fact. Repeated fact. Repeated fact.")
    unique = WorkOutput(
        claims=[
            Candidate(
                key="work_unique",
                kind="work_item",
                status="open",
                statement="Unique fact.",
                citations=[
                    Citation(revision_id=item.revision_id, quote="Unique fact.")
                ],
            )
        ],
        recurring_problem_candidates=[],
        relationships=[],
    )
    normalized = normalize_citations(bundle, unique)
    assert normalized.claims[0].citations[0].start == 0
    assert normalized.claims[0].citations[0].end == len("Unique fact.")

    repeated = unique.model_copy(
        update={
            "claims": [
                unique.claims[0].model_copy(
                    update={
                        "citations": [
                            Citation(
                                revision_id=item.revision_id,
                                quote="Repeated fact.",
                            )
                        ]
                    }
                )
            ]
        }
    )
    with pytest.raises(ValueError, match="not uniquely identified"):
        normalize_citations(bundle, repeated)


def test_auditor_accepts_context_resolved_repeat_and_flags_ambiguous_repeat() -> None:
    bundle, item = context("Alpha repeated. Beta repeated.")
    result = audit(
        bundle,
        DecisionOutput(claims=[], missing_rationale=[], relationships=[]),
        WorkOutput(
            claims=[
                Candidate(
                    key="work_context",
                    kind="work_item",
                    status="open",
                    statement="Beta repeated.",
                    citations=[
                        Citation(
                            revision_id=item.revision_id,
                            quote="repeated.",
                            prefix="Beta ",
                        )
                    ],
                ),
                Candidate(
                    key="work_ambiguous",
                    kind="work_item",
                    status="open",
                    statement="Repeated evidence is ambiguous.",
                    citations=[
                        Citation(revision_id=item.revision_id, quote="repeated.")
                    ],
                ),
            ],
            recurring_problem_candidates=[],
            relationships=[],
        ),
    )
    resolved, ambiguous = result.claims
    assert resolved.content.evidence[0].quote == "repeated."
    assert "invalid_or_ambiguous_citation" not in resolved.flags
    assert ambiguous.content.evidence == []
    assert "invalid_or_ambiguous_citation" in ambiguous.flags
