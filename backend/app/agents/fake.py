import re

from app.schemas.agents import (
    AuditOutput,
    Candidate,
    CandidateLink,
    Citation,
    ContextBundle,
    ContextItem,
    DecisionOutput,
    Dimension,
    Question,
    RubricProposal,
    WorkOutput,
)
from app.schemas.evidence import ClaimKind, ClaimStatus


def _sentences(text: str) -> list[str]:
    return [
        part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", text) if part.strip()
    ]


def _generic_candidates(
    bundle: ContextBundle,
) -> tuple[list[Candidate], list[Candidate]]:
    """Create conservative, source-grounded fixture output for arbitrary evidence.

    The deterministic adapter is used for local/demo runs when Gemini is not
    selected. It must still exercise the same generic workflow contract rather
    than silently depending on one historical fixture.
    """
    decisions: list[Candidate] = []
    work_items: list[Candidate] = []
    seen: set[tuple[str, str]] = set()
    index = 0
    for source in bundle.evidence:
        for sentence in _sentences(source.excerpt):
            lowered = sentence.casefold()
            if len(sentence) < 12:
                continue
            kind: ClaimKind | None = None
            status: ClaimStatus = "unverified"
            target = decisions
            if re.search(r"\b(approved|accepted|agreed|decided|rejected)\b", lowered):
                kind = "decision"
                status = (
                    "accepted"
                    if re.search(r"\b(approved|accepted|agreed|decided)\b", lowered)
                    else "rejected"
                )
            elif re.search(r"\b(blocked|blocking|prevents|cannot proceed)\b", lowered):
                kind, status, target = "blocker", "unresolved", work_items
            elif re.search(
                r"\b(required|must|prerequisite|sign[- ]?off|approval)\b", lowered
            ):
                kind, status, target = "prerequisite", "unresolved", work_items
            elif re.search(
                r"\b(owner|ownership|assigned to|responsible for)\b", lowered
            ):
                kind = "owner"
                status = (
                    "unverified"
                    if re.search(
                        r"\b(unknown|unresolved|unassigned|not assigned|"
                        r"no owner|unclear)\b",
                        lowered,
                    )
                    else "confirmed"
                )
            elif re.search(
                r"\b(todo|to-do|pending|open task|in progress|follow[- ]?up)\b", lowered
            ):
                kind, status, target = "work_item", "open", work_items
            if kind is None:
                continue
            identity = (kind, sentence.casefold())
            if identity in seen:
                continue
            seen.add(identity)
            index += 1
            target.append(
                claim(f"generic_{index}", kind, status, sentence, source, sentence)
            )
    return decisions, work_items


def claim(
    key: str,
    kind: ClaimKind,
    status: ClaimStatus,
    statement: str,
    source: ContextItem,
    quote: str,
) -> Candidate:
    return Candidate(
        key=key,
        kind=kind,
        status=status,
        statement=statement,
        citations=[Citation(revision_id=source.revision_id, quote=quote)],
    )


def decisions(bundle: ContextBundle) -> DecisionOutput:
    candidates = []
    missing = []
    relationships = []
    for item in bundle.evidence:
        excerpt = item.excerpt
        if item.source_id == "PAY-21" and "Friday deployment was proposed" in excerpt:
            candidates.append(
                claim(
                    "friday",
                    "decision",
                    "proposed",
                    "Friday deployment was proposed.",
                    item,
                    "Friday deployment was proposed",
                )
            )
        if item.source_id == "M-07" and "Monday deployment was approved" in excerpt:
            candidates.append(
                claim(
                    "monday",
                    "decision",
                    "accepted",
                    "Monday deployment was conditionally approved.",
                    item,
                    "Monday deployment was approved subject "
                    "to completed payment testing.",
                )
            )
            missing.append(
                "The reason for choosing Monday is missing from the supplied sources."
            )
        if item.source_id == "C-19" and "payment implementation was merged" in excerpt:
            candidates.append(
                claim(
                    "merge",
                    "decision",
                    "implemented",
                    "The payment implementation was merged.",
                    item,
                    "The payment implementation was merged.",
                )
            )
    if {"friday", "monday"} <= {item.key for item in candidates}:
        relationships.append(
            CandidateLink(origin="monday", target="friday", relation="supersedes")
        )
    generic_decisions, _ = _generic_candidates(bundle)
    known = {(item.kind, item.statement.casefold()) for item in candidates}
    candidates.extend(
        item
        for item in generic_decisions
        if (item.kind, item.statement.casefold()) not in known
    )
    return DecisionOutput(
        claims=candidates[:8], missing_rationale=missing, relationships=relationships
    )


def work(bundle: ContextBundle) -> WorkOutput:
    candidates = []
    relationships = []
    for item in bundle.evidence:
        if item.source_id != "M-07":
            continue
        for key, kind, quote in [
            ("work_testing", "prerequisite", "Testing has not been signed off."),
            ("work_rollback", "blocker", "Rollback ownership is unresolved."),
        ]:
            if quote not in item.excerpt:
                continue
            category: ClaimKind = (
                "prerequisite" if kind == "prerequisite" else "blocker"
            )
            candidates.append(claim(key, category, "unresolved", quote, item, quote))
            if "Monday deployment was approved" in item.excerpt:
                relationships.append(
                    CandidateLink(origin="monday", target=key, relation="requires")
                )
    _, generic_work = _generic_candidates(bundle)
    known = {(item.kind, item.statement.casefold()) for item in candidates}
    candidates.extend(
        item
        for item in generic_work
        if (item.kind, item.statement.casefold()) not in known
    )
    return WorkOutput(
        claims=candidates[:12],
        recurring_problem_candidates=[],
        relationships=relationships,
    )


def rehearsal(bundle: ContextBundle, audit: AuditOutput) -> RubricProposal:
    source = next(
        (item for item in bundle.evidence if item.source_id == "M-07"),
        bundle.evidence[0],
    )
    known_scenario = {"monday", "work_testing", "work_rollback"} <= {
        item.key for item in audit.claims
    }
    dimensions: list[Dimension] = ["action", "prerequisites", "evidence", "escalation"]
    prompts = (
        [
            (
                "What is the safe next action?",
                "Wait for testing and identify a rollback owner.",
            ),
            ("Which prerequisite is pending?", "Payment testing must be signed off."),
            (
                "Which record authorizes Monday conditionally?",
                "M-07 records the approval.",
            ),
            ("What should you escalate?", "The missing rollback owner."),
        ]
        if known_scenario
        else [
            (
                "What is the safe next action?",
                "Confirm the task and dependencies with the reviewer.",
            ),
            (
                "How should you handle prerequisites?",
                "Verify each prerequisite before acting.",
            ),
            (
                "Which evidence should you verify?",
                f"Review the source revision for {source.source_id}.",
            ),
            (
                "What should you escalate?",
                "Ask the reviewer about missing evidence or access.",
            ),
        ]
    )
    return RubricProposal(
        title="Scoped handover rehearsal",
        questions=[
            Question(
                dimension=dimension,
                prompt=prompt,
                choices=["Proceed without checking", answer],
                correct_choice=1,
                weight=weight,
                explanation=answer,
                evidence_revision_ids=[source.revision_id],
            )
            for dimension, weight, (prompt, answer) in zip(
                dimensions, [30, 25, 25, 20], prompts, strict=True
            )
        ],
    )
