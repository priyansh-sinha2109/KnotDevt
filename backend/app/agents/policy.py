import re
from dataclasses import dataclass

from app.schemas.agents import Candidate
from app.schemas.evidence import ClaimStatus

UNCERTAIN = re.compile(
    r"\b(?:does not identify|not identified|not named|none listed|unknown|unclear|"
    r"unassigned|no confirmed|no verified|not confirmed)\b",
    re.I,
)
OWNERSHIP = re.compile(
    r"\b(?:owns?|owner|assigned to|assignee|responsible for|accountable for)\b", re.I
)
OWNER_SUBJECT = re.compile(
    r"(?:\b([A-Za-z0-9_.-]+)\s+(?:owns?|is\s+assigned|is\s+responsible)|"
    r"\b(?:assignees?|owner)\s*:\s*([A-Za-z0-9_.\[\]-]+))",
    re.I,
)
AUTHORSHIP_ONLY = re.compile(r"\b(?:author|authored|reported|opened|submitted)\b", re.I)
DECISION = re.compile(
    r"\b(?:approved|accepted|decided|selected|chose|agreed|authorized|rejected|"
    r"superseded)\b",
    re.I,
)
IMPLEMENTATION = re.compile(
    r"\b(?:implemented|deployed|released|merged|fixed|resolved|completed|shipped)\b",
    re.I,
)


@dataclass(frozen=True)
class CandidatePolicy:
    status: ClaimStatus
    flags: tuple[str, ...] = ()


def candidate_policy(candidate: Candidate) -> CandidatePolicy:
    """Fail closed for high-impact statuses that lack structural support.

    This is not a semantic verifier. It only rejects common category/status
    escalations whose own statement and cited text do not contain the required
    evidence shape; remaining meaning is explicitly left for human review.
    """
    statement = candidate.statement
    quoted = " ".join(citation.quote for citation in candidate.citations)
    if candidate.kind in {"owner", "contact"} and UNCERTAIN.search(statement):
        return CandidatePolicy(
            "unresolved" if candidate.kind == "owner" else "unverified",
            ("uncertain_identity",),
        )
    if candidate.kind == "owner" and candidate.status == "confirmed":
        if AUTHORSHIP_ONLY.search(statement) and not OWNERSHIP.search(statement):
            return CandidatePolicy("unverified", ("unsupported_ownership",))
        # Ownership must be asserted by the candidate statement itself. A cited
        # paragraph can mention another, unresolved owner and must not lend that
        # ownership to the named subject.
        if not OWNERSHIP.search(statement):
            return CandidatePolicy("unverified", ("unsupported_ownership",))
        subjects = {
            value.casefold()
            for match in OWNER_SUBJECT.finditer(quoted)
            for value in match.groups()
            if value
        }
        statement_tokens = set(re.findall(r"[A-Za-z0-9_.\[\]-]+", statement.casefold()))
        if not subjects & statement_tokens:
            return CandidatePolicy("unverified", ("unsupported_ownership",))
    if candidate.kind == "contact" and candidate.status == "confirmed":
        if not re.search(r"\b(?:contact|escalate to|reach out to)\b", quoted, re.I):
            return CandidatePolicy("unverified", ("unsupported_contact",))
    if candidate.kind == "decision" and candidate.status in {"accepted", "resolved"}:
        if not DECISION.search(quoted):
            return CandidatePolicy("unverified", ("unsupported_decision_status",))
    if candidate.kind == "decision" and candidate.status == "implemented":
        if not IMPLEMENTATION.search(quoted):
            return CandidatePolicy("unverified", ("unsupported_completion",))
    if candidate.status in {"implemented", "resolved"} and not IMPLEMENTATION.search(
        quoted
    ):
        return CandidatePolicy("unverified", ("unsupported_completion",))
    return CandidatePolicy(candidate.status)


def duplicate_identity(candidate: Candidate) -> tuple[object, ...]:
    """Stable identity for genuinely repeated findings, not topical similarity."""
    citations = tuple(
        sorted(
            (
                str(item.revision_id),
                item.relation,
                " ".join(item.quote.split()).casefold(),
            )
            for item in candidate.citations
        )
    )
    statement = " ".join(candidate.statement.split()).casefold().rstrip(".")
    return candidate.kind, candidate.status, statement, citations


def finding_identity(candidate: Candidate) -> tuple[object, ...]:
    citations = tuple(
        sorted(
            (
                str(item.revision_id),
                item.relation,
                " ".join(item.quote.split()).casefold(),
            )
            for item in candidate.citations
        )
    )
    return " ".join(candidate.statement.split()).casefold().rstrip("."), citations
