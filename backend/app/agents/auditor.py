from app.schemas.agents import (
    AuditedClaim,
    AuditOutput,
    ContextBundle,
    DecisionOutput,
    WorkOutput,
)
from app.schemas.evidence import ClaimContent, EvidencePointer


def audit(
    bundle: ContextBundle, decisions: DecisionOutput, work: WorkOutput
) -> AuditOutput:
    candidates = decisions.claims + work.claims
    if len({item.key for item in candidates}) != len(candidates):
        raise ValueError("Conflicting candidate keys")
    dependencies = {
        link.target
        for link in decisions.relationships + work.relationships
        if link.relation == "requires"
    }
    sources = {item.revision_id: item.excerpt for item in bundle.evidence}
    claims = []
    for item in candidates:
        evidence = []
        flags = []
        seen = set()
        for citation in item.citations:
            excerpt = sources.get(citation.revision_id, "")
            offset = excerpt.find(citation.quote)
            if offset < 0 or excerpt.find(citation.quote, offset + 1) >= 0:
                flags.append("invalid_or_ambiguous_citation")
                continue
            key = citation.revision_id, citation.relation, offset
            if key in seen:
                continue
            seen.add(key)
            evidence.append(
                EvidencePointer(
                    revision_id=citation.revision_id,
                    start=offset,
                    end=offset + len(citation.quote),
                    quote=citation.quote,
                    relation=citation.relation,
                )
            )
        supporting = any(pointer.relation == "supports" for pointer in evidence)
        if not supporting:
            flags.append("supporting_evidence_missing")
        if any(pointer.relation == "contradicts" for pointer in evidence):
            flags.append("contradictory_evidence")
        status = item.status
        if not supporting and status != "unresolved":
            status = "unverified"
        if (
            item.key in dependencies
            or item.kind in {"prerequisite", "blocker", "owner", "risk"}
            or status in {"unverified", "unresolved", "open", "conflicting", "proposed"}
        ):
            flags.append("critical_gap_review_required")
        claims.append(
            AuditedClaim(
                key=item.key,
                flags=flags,
                content=ClaimContent(
                    kind=item.kind,
                    status=status,
                    statement=item.statement,
                    evidence=evidence,
                ),
            )
        )
    keys = {item.key for item in claims}
    links = [
        link
        for link in decisions.relationships + work.relationships
        if link.origin in keys and link.target in keys and link.origin != link.target
    ]
    return AuditOutput(
        claims=claims,
        relationships=links,
        unresolved=decisions.missing_rationale + bundle.unresolved_ids,
    )
