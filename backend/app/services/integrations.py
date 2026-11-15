"""Tenant-authorized tool connections and transactional source normalization."""

import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.cache import redis_client
from app.core.config import settings
from app.db.integrations import Connection
from app.db.sources import ImportPayload, Job, Source
from app.integrations import providers
from app.schemas.sources import IMPORT_INPUT
from app.services.access import EDITORS, ProjectAccess, audit, require_project
from app.services.imports import import_revisions


def cipher() -> Fernet:
    key = settings().integration_encryption_key
    if not key:
        raise HTTPException(503, "Connector token encryption is not configured")
    try:
        return Fernet(key.get_secret_value().encode())
    except ValueError:
        raise HTTPException(503, "Connector encryption key is invalid") from None


def encrypt(value: dict[str, Any]) -> str:
    return cipher().encrypt(json.dumps(value).encode()).decode()


def decrypt(value: str) -> dict[str, Any]:
    return json.loads(cipher().decrypt(value.encode()))  # type: ignore[no-any-return]


def connection_for(db: Session, connection_id: UUID, user_id: UUID) -> Connection:
    row = db.scalar(
        select(Connection).where(Connection.id == connection_id).with_for_update()
    )
    if row is None:
        raise HTTPException(404, "Connection not found")
    require_project(db, row.project_id, user_id).require(EDITORS)
    if row.owner_id != user_id:
        raise HTTPException(404, "Connection not found")
    return row


def view(row: Connection) -> dict[str, Any]:
    return {
        key: getattr(row, key)
        for key in (
            "id",
            "provider",
            "name",
            "status",
            "selected_resources",
            "last_sync_at",
            "last_attempt_at",
            "next_sync_at",
            "last_error",
            "imported_count",
        )
    }


def list_tools(db: Session, access: ProjectAccess) -> dict[str, Any]:
    rows = db.scalars(
        select(Connection).where(
            Connection.project_id == access.project.id,
            Connection.owner_id == access.user_id,
            Connection.status != "disconnected",
        )
    ).all()
    return {
        "items": [
            {
                "provider": provider,
                "configured": providers.configured(provider),
                "setup_message": None
                if providers.configured(provider)
                else (
                    "An administrator must configure the OAuth app "
                    "and encrypted token storage."
                ),
                "connections": [view(row) for row in rows if row.provider == provider],
            }
            for provider in providers.PROVIDERS
        ]
    }


def start_oauth(access: ProjectAccess, provider: str) -> str:
    access.require(EDITORS)
    if provider not in providers.PROVIDERS:
        raise HTTPException(404, "Unknown connector")
    if not providers.configured(provider):
        raise HTTPException(
            503,
            "Configure the provider OAuth app and encrypted token storage first",
        )
    cipher()
    state = secrets.token_urlsafe(32)
    redis_client().setex(
        "connector-oauth:" + state,
        600,
        json.dumps(
            {
                "project": str(access.project.id),
                "actor": str(access.user_id),
                "provider": provider,
            }
        ),
    )
    return providers.authorize_url(provider, state)


def finish_oauth(
    db: Session, provider: str, state: str, code: str
) -> tuple[UUID, UUID]:
    saved = redis_client().getdel("connector-oauth:" + state)
    if not saved:
        raise HTTPException(400, "Authorization state expired or already used")
    context = json.loads(cast(bytes, saved))
    if context["provider"] != provider:
        raise HTTPException(403, "Authorization state does not match this provider")
    # Provider redirects land on the public callback host, so the localhost
    # browser session cookie is intentionally unavailable here. The one-use,
    # short-lived state record is bound to the initiating actor and project.
    actor = UUID(context["actor"])
    access = require_project(db, UUID(context["project"]), actor)
    access.require(EDITORS)
    token = providers.exchange(provider, code)
    identities = providers.identities(provider, token)
    if not identities:
        raise HTTPException(403, "No authorized installations or sites were returned")
    for identity in identities:
        existing = db.scalar(
            select(Connection)
            .where(
                Connection.project_id == access.project.id,
                Connection.owner_id == actor,
                Connection.provider == provider,
                Connection.external_id == identity["id"],
            )
            .with_for_update()
        )
        row = existing or Connection(
            project_id=access.project.id,
            owner_id=actor,
            provider=provider,
            external_id=identity["id"],
            name=identity["name"],
        )
        row.credential = encrypt(token)
        row.status, row.last_error = "connected", None
        row.scopes = (
            str(token.get("scope", providers.SCOPES[provider]))
            .replace(",", " ")
            .split()
        )
        row.cursor = {"site_url": identity.get("url", "")}
        db.add(row)
    audit(db, actor, "integration.connected", project=access.project)
    db.commit()
    return access.project.workspace_id, access.project.id


def access_token(row: Connection) -> str:
    if not row.credential or row.status == "disconnected":
        raise providers.RemoteError(
            "needs_reauthorization", "Connection has been disconnected."
        )
    token = decrypt(row.credential)
    expires = token.get("expires_in")
    if (
        expires
        and float(token.get("obtained_at", 0)) + float(expires)
        < datetime.now(UTC).timestamp() + 60
    ):
        if not token.get("refresh_token"):
            raise providers.RemoteError(
                "needs_reauthorization",
                "Authorization expired. Connect this tool again.",
            )
        c = settings()
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": token["refresh_token"],
            "client_id": getattr(c, row.provider + "_client_id"),
            "client_secret": getattr(
                c, row.provider + "_client_secret"
            ).get_secret_value(),
        }
        url = {
            "jira": "https://auth.atlassian.com/oauth/token",
            "slack": "https://slack.com/api/oauth.v2.access",
            "github": "https://github.com/login/oauth/access_token",
        }[row.provider]
        updated = providers.request(
            "POST",
            url,
            headers={"Accept": "application/json"},
            **({"json": payload} if row.provider == "jira" else {"data": payload}),
        )
        if not updated.get("access_token"):
            raise providers.RemoteError(
                "needs_reauthorization",
                "Provider authorization could not be refreshed.",
            )
        token.update(updated)
        token["obtained_at"] = datetime.now(UTC).timestamp()
        row.credential = encrypt(token)
    return str(token["access_token"])


def list_resources(db: Session, row: Connection) -> list[dict[str, str]]:
    try:
        result = providers.resources(row.provider, access_token(row), row.external_id)
        db.commit()
        return result
    except providers.RemoteError as error:
        row.status, row.last_error = error.status, error.message
        if error.status in {"needs_reauthorization", "permission_denied"}:
            hide_sources(db, row)
        db.commit()
        raise HTTPException(503, error.message) from None


def select_resources(db: Session, row: Connection, ids: list[str]) -> None:
    permitted = {item["id"]: item for item in list_resources(db, row)}
    require_project(db, row.project_id, row.owner_id).require(EDITORS)
    if any(value not in permitted for value in ids):
        raise HTTPException(403, "Select only resources returned by this connection")
    removed = {item["id"] for item in row.selected_resources} - set(ids)
    for source in db.scalars(
        select(Source).where(
            Source.connection_id == row.id, Source.external_resource_id.in_(removed)
        )
    ):
        source.deleted_at = datetime.now(UTC)
        source.policy_revision += 1
    row.selected_resources = [permitted[value] for value in dict.fromkeys(ids)]
    row.cursor = {"site_url": row.cursor.get("site_url", "")}
    row.status = "connected"
    db.commit()


def schedule(db: Session, row: Connection) -> None:
    if not row.credential or row.status == "disconnected":
        raise HTTPException(409, "Reconnect this tool first")
    if not row.selected_resources:
        raise HTTPException(409, "Select at least one permitted resource")
    # Preserve a server-requested cooldown and never reset a running cursor.
    if (
        row.status == "rate_limited"
        and row.next_sync_at
        and row.next_sync_at > datetime.now(UTC)
    ):
        raise HTTPException(429, "Wait until the provider cooldown has elapsed")
    row.next_sync_at = datetime.now(UTC)
    db.commit()
    try:
        from app.workers.connector_app import celery

        celery.send_task(
            "knotdevt.connectors.sync",
            args=[str(row.id)],
            queue="knotdevt-connectors",
            retry=False,
        )
    except Exception:
        pass  # Durable next_sync_at is recovered by connector Beat.


def hide_sources(db: Session, row: Connection) -> None:
    db.execute(
        text("SELECT set_config('knotdevt.project_id', :project, true)"),
        {"project": str(row.project_id)},
    )
    sources = db.scalars(
        select(Source).where(
            Source.project_id == row.project_id,
            Source.owner_id == row.owner_id,
            Source.provider == row.provider,
            Source.original_id.like("ext-" + row.id.hex + "-%"),
        )
    ).all()
    for source in sources:
        source.deleted_at = datetime.now(UTC)
        source.policy_revision += 1


def disconnect(db: Session, row: Connection) -> None:
    row.status, row.credential, row.next_sync_at = "disconnected", None, None
    row.selected_resources = []
    hide_sources(db, row)
    audit(
        db,
        row.owner_id,
        "integration.disconnected",
        project=require_project(db, row.project_id, row.owner_id).project,
        target_id=row.id,
    )
    db.commit()


def sync_page(db: Session, row: Connection) -> None:
    access = require_project(db, row.project_id, row.owner_id)
    access.require(EDITORS)
    token = access_token(row)
    permitted = {
        x["id"] for x in providers.resources(row.provider, token, row.external_id)
    }
    if any(x["id"] not in permitted for x in row.selected_resources):
        raise providers.RemoteError(
            "permission_denied", "A selected resource is no longer authorized."
        )
    index = int(row.cursor.get("resource_index", 0))
    resource = row.selected_resources[index]
    cursor = dict(row.cursor.get("page", {}))
    cursor["site_url"] = row.cursor.get("site_url", "")
    records, next_cursor, finished = providers.fetch_page(
        row.provider, token, row.external_id, resource, cursor
    )
    if records:
        entries = [
            {
                "source_id": "ext-"
                + row.id.hex
                + "-"
                + providers.stable_id(str(row.id), resource["id"], record["id"])[4:],
                "author": record["author"][:160],
                "reference": record["url"],
                "event_at": record["at"],
                "event_type": record["type"],
                "text": record["text"]
                if len(record["text"]) <= 12000
                else record["text"][:11920]
                + "\n[Snapshot truncated; consult original source for full content.]",
                "access": "restricted",
            }
            for record in records
        ]
        kind = "conversation-notes" if row.provider == "slack" else "issue-events"
        raw = json.dumps(
            {
                "kind": kind,
                "provider": row.provider,
                "notes" if row.provider == "slack" else "events": entries,
            }
        ).encode()
        batch = IMPORT_INPUT.validate_json(raw)
        job = Job(
            project_id=row.project_id,
            actor_id=row.owner_id,
            kind="import",
            queue="knotdevt-connectors",
            input_hash=hashlib.sha256(raw).hexdigest(),
            state="succeeded",
            attempts=1,
        )
        db.add(job)
        db.flush()
        db.add(ImportPayload(job_id=job.id, original=raw))
        db.flush()
        # Restore only snapshots whose exact resource has just passed authorization.
        for retained_source in db.scalars(
            select(Source).where(
                Source.connection_id == row.id,
                Source.external_resource_id == resource["id"],
                Source.original_id.in_([entry["source_id"] for entry in entries]),
            )
        ):
            retained_source.deleted_at = None
        import_revisions(db, access, job, batch)
        for record, entry in zip(records, entries, strict=True):
            source = db.scalar(
                select(Source).where(
                    Source.project_id == row.project_id,
                    Source.original_id == entry["source_id"],
                    Source.provider == row.provider,
                )
            )
            if source:
                source.connection_id = row.id
                source.external_resource_id = resource["id"]
                source.external_object_id = record["id"]
    site = row.cursor.get("site_url", "")
    if finished and index + 1 == len(row.selected_resources):
        row.cursor = {"site_url": site}
        row.status, row.last_sync_at = "synced", datetime.now(UTC)
        row.next_sync_at = datetime.now(UTC) + timedelta(minutes=30)
    else:
        row.cursor = {
            "site_url": site,
            "resource_index": index + 1 if finished else index,
            "page": {} if finished else next_cursor,
        }
        row.status = "syncing"
        row.next_sync_at = datetime.now(UTC) + timedelta(
            seconds=65 if row.provider == "slack" else 5
        )
    row.last_error = None
    row.imported_count = len(
        db.scalars(
            select(Source.id).where(
                Source.project_id == row.project_id,
                Source.original_id.like("ext-" + row.id.hex + "-%"),
            )
        ).all()
    )
