import re

from app.schemas.agents import AuditedClaim, AuditOutput, ContextBundle
from app.schemas.evidence import ClaimContent, ClaimKind, ClaimStatus, EvidencePointer

HEADER = re.compile(
    r"^GitHub Issue #\d+ is an automatically generated Renovate Dependency Dashboard\b",
    re.I,
)
FIELDS: tuple[tuple[str, ClaimKind, ClaimStatus, str], ...] = (
    ("dashboard", "overview", "confirmed", HEADER.pattern),
    (
        "pending_checks",
        "work_item",
        "open",
        r"^Several dependency updates are awaiting status checks\b",
    ),
    ("open_updates", "work_item", "open", r"^Open update pull requests include\b"),
    (
        "blocked_update",
        "blocker",
        "unresolved",
        r"^The .+ update is blocked by a previously closed pull request #\d+\b",
    ),
)


def dashboard_summary(bundle: ContextBundle) -> AuditOutput | None:
    """Extract recognized status sentences from a sole dashboard summary."""
    if len(bundle.evidence) != 1:
        return None
    source = bundle.evidence[0]
    if source.event_type != "task" or not HEADER.match(source.excerpt):
        return None
    sentences = re.split(r"(?<=[.!?])\s+", source.excerpt.strip())
    closing = (
        "The issue remains open and tracks outstanding dependency maintenance work."
    )
    if any(
        sentence != closing
        and not any(re.match(pattern, sentence, re.I) for _, _, _, pattern in FIELDS)
        for sentence in sentences
    ):
        return None

    claims = []
    for key, kind, status, pattern in FIELDS:
        matches = [
            sentence
            for sentence in sentences
            if sentence.endswith(".") and re.match(pattern, sentence, re.I)
        ]
        if len(matches) != 1:
            continue
        quote = matches[0]
        start = source.excerpt.index(quote)
        flags = ["semantic_review_required"]
        if kind == "blocker":
            flags.append("critical_gap_review_required")
        claims.append(
            AuditedClaim(
                key=key,
                flags=flags,
                content=ClaimContent(
                    kind=kind,
                    status=status,
                    statement=quote,
                    evidence=[
                        EvidencePointer(
                            revision_id=source.revision_id,
                            start=start,
                            end=start + len(quote),
                            quote=quote,
                            relation="supports",
                        )
                    ],
                ),
            )
        )
    # Fall back to reviewed model candidates for unrecognized dashboard formats.
    if len(claims) != len(FIELDS):
        return None
    unresolved = list(bundle.unresolved_ids)
    if not re.search(
        r"\b(?:owner|assignee|responsible|assigned)\b", source.excerpt, re.I
    ):
        unresolved.append(
            "The imported dashboard summary does not identify a confirmed human owner."
        )
    return AuditOutput(
        claims=claims,
        relationships=[],
        unresolved=unresolved,
    )
