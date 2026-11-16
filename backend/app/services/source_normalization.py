"""Deterministic, display-safe normalization for imported source records."""

import json
from dataclasses import dataclass

from app.db.sources import Source, SourceRevision


@dataclass(frozen=True)
class NormalizedSource:
    title: str
    record_type: str
    summary: str


def normalize_source(source: Source, revision: SourceRevision) -> NormalizedSource:
    payload: object | None = None
    try:
        payload = json.loads(revision.excerpt)
    except (TypeError, ValueError):
        pass
    data = payload if isinstance(payload, dict) else {}
    provider = source.provider.replace("-", " ").title()
    event = revision.event_type.replace("_", " ").replace("-", " ").strip().title()
    record_type = f"{provider} {event}".strip() or "Imported source record"

    commit = data.get("commit") if isinstance(data.get("commit"), dict) else {}
    title = next(
        (
            value.strip()
            for value in (
                commit.get("message") if isinstance(commit, dict) else None,
                data.get("title"),
                data.get("summary"),
                data.get("full_name"),
                data.get("name"),
            )
            if isinstance(value, str) and value.strip()
        ),
        f"{record_type} · {source.original_id}",
    )
    if "message" in commit and isinstance(commit["message"], str):
        summary = f"Recorded commit activity in {data.get('full_name') or data.get('repository') or source.original_id}."
    elif isinstance(data.get("body"), str) and data["body"].strip():
        summary = " ".join(data["body"].split())[:280]
    elif isinstance(data.get("description"), str) and data["description"].strip():
        summary = " ".join(data["description"].split())[:280]
    else:
        summary = f"Original {record_type.lower()} imported from {source.original_id}."
    return NormalizedSource(title=title[:180], record_type=record_type[:100], summary=summary[:320])
