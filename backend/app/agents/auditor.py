import re

from app.agents.citations import resolve_citation
from app.agents.dashboard import dashboard_summary
from app.agents.github_snapshot import SnapshotMetadata, github_snapshot
from app.agents.policy import candidate_policy, duplicate_identity, finding_identity
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
    dashboard = dashboard_summary(bundle)
    if dashboard is not None:
        return dashboard
    candidates = []
    identities = set()
    decision_findings = set()
    for item in decisions.claims:
        # Stage contracts are also enforced locally. A model cannot use the
        # Decision Analyst channel to create ownership, blocker or work claims.
        if item.kind not in {"decision", "overview"}:
            continue
        identity = duplicate_identity(item)
        if identity in identities:
            continue
        identities.add(identity)
        decision_findings.add(finding_identity(item))
        candidates.append(item)
    for item in work.claims:
        normalized_statement = " ".join(item.statement.split()).casefold().rstrip(".")
        normalized_task = " ".join(bundle.task.split()).casefold().rstrip(".")
        if normalized_statement == normalized_task and not any(
            normalized_statement in " ".join(citation.quote.split()).casefold()
            for citation in item.citations
        ):
            continue
        # The same sentence and citations must not become both a decision and a
        # work item. Distinct prerequisite/risk/blocker meanings remain allowed.
        if item.kind == "work_item" and finding_identity(item) in decision_findings:
            continue
        identity = duplicate_identity(item)
        if identity in identities:
            continue
        identities.add(identity)
        candidates.append(item)
    if len({item.key for item in candidates}) != len(candidates):
        raise ValueError("Conflicting candidate keys")
    dependencies = {
        link.target
        for link in decisions.relationships + work.relationships
        if link.relation == "requires"
    }
    sources = {item.revision_id: item.excerpt for item in bundle.evidence}
    metadata: dict[object, SnapshotMetadata] = {
        item.revision_id: parsed
        for item in bundle.evidence
        if (parsed := github_snapshot(item)) is not None
    }
    claims = []
    for item in candidates:
        evidence = []
        policy = candidate_policy(item)
        flags = ["semantic_review_required", *policy.flags]
        seen = set()
        for citation in item.citations:
            excerpt = sources.get(citation.revision_id, "")
            resolved = resolve_citation(excerpt, citation)
            if resolved is None:
                flags.append("invalid_or_ambiguous_citation")
                continue
            key = (
                citation.revision_id,
                citation.relation,
                resolved.start,
                resolved.end,
            )
            if key in seen:
                continue
            seen.add(key)
            evidence.append(
                EvidencePointer(
                    revision_id=citation.revision_id,
                    start=resolved.start,
                    end=resolved.end,
                    quote=citation.quote,
                    relation=citation.relation,
                )
            )
        supporting = any(pointer.relation == "supports" for pointer in evidence)
        if not supporting:
            flags.append("supporting_evidence_missing")
        if any(pointer.relation == "contradicts" for pointer in evidence):
            flags.append("contradictory_evidence")
        status = policy.status
        if not supporting and status != "unresolved":
            status = "unverified"
        supporting_pointers = [
            pointer for pointer in evidence if pointer.relation == "supports"
        ]
        closed_snapshot_support = supporting_pointers and all(
            (snapshot := metadata.get(pointer.revision_id)) is not None
            and snapshot.state == "closed"
            for pointer in supporting_pointers
        )
        explicit_ongoing = any(
            re.search(
                r"\b(?:still|remains?|pending|unresolved|not fixed|incomplete|"
                r"blocked|open)\b",
                pointer.quote,
                re.I,
            )
            for pointer in supporting_pointers
        )
        if status == "open" and closed_snapshot_support and not explicit_ongoing:
            status = "unverified"
            flags.append("closed_snapshot_open_status_unverified")
        if (
            item.key in dependencies
            or item.kind in {"prerequisite", "blocker", "owner", "risk"}
            or status in {"unverified", "unresolved", "open", "conflicting", "proposed"}
        ):
            flags.append("critical_gap_review_required")
        claims.append(
            AuditedClaim(
                key=item.key,
                flags=list(dict.fromkeys(flags)),
                content=ClaimContent(
                    kind=item.kind,
                    status=status,
                    statement=item.statement,
                    evidence=evidence,
                ),
            )
        )
    unresolved = decisions.missing_rationale + bundle.unresolved_ids
    for index, source in enumerate(bundle.evidence, start=1):
        snapshot = metadata.get(source.revision_id)
        if snapshot is None:
            continue
        state_covered = any(
            claim.content.kind == "overview"
            and snapshot.state in claim.content.statement.casefold()
            and any(
                pointer.revision_id == source.revision_id
                for pointer in claim.content.evidence
            )
            for claim in claims
        )
        if not state_covered:
            claims.append(
                AuditedClaim(
                    key=f"snapshot_state_{index}",
                    flags=["semantic_review_required"],
                    content=ClaimContent(
                        kind="overview",
                        status="confirmed",
                        statement=(
                            f"Issue state at the imported snapshot: {snapshot.state}."
                        ),
                        evidence=[
                            EvidencePointer(
                                revision_id=source.revision_id,
                                start=snapshot.state_start,
                                end=snapshot.state_start + len(snapshot.state_quote),
                                quote=snapshot.state_quote,
                                relation="supports",
                            )
                        ],
                    ),
                )
            )
        for assignee_index, assignee in enumerate(snapshot.assignees, start=1):
            assignee_covered = any(
                claim.content.kind == "owner"
                and assignee.casefold() in claim.content.statement.casefold()
                and claim.content.status == "confirmed"
                for claim in claims
            )
            if assignee_covered:
                continue
            claims.append(
                AuditedClaim(
                    key=f"snapshot_assignee_{index}_{assignee_index}",
                    flags=[
                        "semantic_review_required",
                        "critical_gap_review_required",
                    ],
                    content=ClaimContent(
                        kind="owner",
                        status="confirmed",
                        statement=(
                            f"Explicit issue assignee at the snapshot: {assignee}."
                        ),
                        evidence=[
                            EvidencePointer(
                                revision_id=source.revision_id,
                                start=snapshot.assignee_start,
                                end=(
                                    snapshot.assignee_start
                                    + len(snapshot.assignee_quote)
                                ),
                                quote=snapshot.assignee_quote,
                                relation="supports",
                            )
                        ],
                    ),
                )
            )
        if snapshot.state == "closed":
            unresolved.append(
                "The imported issue snapshot is closed, but closure alone does not "
                "verify that a fix was implemented."
            )
        if not snapshot.assignees and not any(
            claim.content.kind == "owner"
            and any(
                pointer.revision_id == source.revision_id
                for pointer in claim.content.evidence
            )
            for claim in claims
        ):
            unresolved.append(
                "The imported issue snapshot lists no assignee; this does not prove "
                "that no owner exists."
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
        unresolved=list(dict.fromkeys(unresolved)),
    )
