import hashlib
import hmac
import json
import time
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import Field
from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert

from app.api.dependencies import DB, Actor
from app.core.config import settings
from app.db.integrations import Connection, IntegrationEvent
from app.db.sources import Source, SourceAccessRule
from app.db.identity import ProjectMembership, Role
from app.integrations import providers
from app.schemas.integrations import IntegrationList, ResourceList
from app.schemas.sources import StrictModel
from app.services import integrations as service
from app.services.access import EDITORS, require_project

router = APIRouter(tags=["integrations"])


class ResourceSelection(StrictModel):
    resource_ids: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=160)]], Field(max_length=20)
    ]


@router.post("/integrations/{connection_id}/share-with-recipients")
def share_with_recipients(connection_id: UUID, identity: Actor, db: DB) -> dict[str, int]:
    """Grant assigned project recipients read access to this connector's sources."""
    row = db.get(Connection, connection_id)
    if row is None or row.status == "disconnected":
        raise HTTPException(404, "Integration connection not found")
    access = require_project(db, row.project_id, identity.user.id)
    access.require(EDITORS)
    recipients = set(db.scalars(select(ProjectMembership.user_id).where(
        ProjectMembership.project_id == row.project_id,
        ProjectMembership.role == Role.RECIPIENT,
    )))
    sources = db.scalars(select(Source).where(
        Source.connection_id == row.id,
        Source.owner_id == identity.user.id,
        Source.deleted_at.is_(None),
        Source.restricted.is_(True),
    )).all()
    added = 0
    for source in sources:
        existing = set(db.scalars(select(SourceAccessRule.user_id).where(
            SourceAccessRule.source_id == source.id
        )))
        for user_id in recipients - existing:
            db.add(SourceAccessRule(source_id=source.id, user_id=user_id))
            added += 1
    db.commit()
    return {"sources": len(sources), "recipients": len(recipients), "grants_added": added}


@router.get("/projects/{project_id}/integrations", response_model=IntegrationList)
def list_tools(project_id: UUID, identity: Actor, db: DB) -> dict[str, Any]:
    return service.list_tools(db, require_project(db, project_id, identity.user.id))


@router.post("/projects/{project_id}/integrations/{provider}/connect")
def connect(project_id: UUID, provider: str, identity: Actor, db: DB) -> dict[str, str]:
    return {
        "authorization_url": service.start_oauth(
            require_project(db, project_id, identity.user.id), provider
        )
    }


@router.get("/integrations/{provider}/callback")
def callback(
    provider: str,
    db: DB,
    state: Annotated[str, Query(min_length=32, max_length=200)],
    # Atlassian 3LO codes can exceed 1 KiB; keep a bounded limit while
    # accepting valid provider responses.
    code: Annotated[str, Query(min_length=1, max_length=4096)],
) -> RedirectResponse:
    try:
        workspace, project = service.finish_oauth(
            db, provider, state, code
        )
    except providers.RemoteError as error:
        raise HTTPException(503, error.message) from None
    config = settings()
    return RedirectResponse(
        f"{config.frontend_url.rstrip('/')}/app?workspace={workspace}&project={project}&view=sources",
        status_code=303,
    )


@router.get("/integrations/{connection_id}/resources", response_model=ResourceList)
def resources(connection_id: UUID, identity: Actor, db: DB) -> dict[str, Any]:
    return {
        "items": service.list_resources(
            db, service.connection_for(db, connection_id, identity.user.id)
        )
    }


@router.post("/integrations/{connection_id}/resources", status_code=204)
def select_resources(
    connection_id: UUID, body: ResourceSelection, identity: Actor, db: DB
) -> None:
    row = service.connection_for(db, connection_id, identity.user.id)
    if row.status == "syncing":
        raise HTTPException(409, "Wait for the active sync before changing resources")
    service.select_resources(db, row, body.resource_ids)


@router.post("/integrations/{connection_id}/sync", status_code=202)
def sync(connection_id: UUID, identity: Actor, db: DB) -> dict[str, str]:
    service.schedule(db, service.connection_for(db, connection_id, identity.user.id))
    return {"status": "scheduled"}


@router.post("/integrations/{connection_id}/disconnect", status_code=204)
def disconnect(connection_id: UUID, identity: Actor, db: DB) -> None:
    row = db.scalar(
        select(Connection).where(Connection.id == connection_id).with_for_update()
    )
    if row is None:
        raise HTTPException(404, "Connection not found")
    service.connection_for(db, connection_id, identity.user.id)
    service.disconnect(db, row)


@router.post("/integrations/webhooks/{provider}")
async def webhook(provider: str, request: Request, db: DB) -> dict[str, Any]:
    if provider not in ("github", "slack"):
        raise HTTPException(404, "This provider webhook is not enabled")
    config = settings()
    secret = (
        config.github_webhook_secret
        if provider == "github"
        else config.slack_signing_secret
    )
    if secret is None:
        raise HTTPException(503, "Webhook verification is not configured")
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > 1048576:
            raise HTTPException(413, "Webhook is too large")
        raw.extend(chunk)
    payload = bytes(raw)
    if provider == "github":
        supplied = request.headers.get("x-hub-signature-256", "")
        expected = (
            "sha256="
            + hmac.new(
                secret.get_secret_value().encode(), payload, hashlib.sha256
            ).hexdigest()
        )
        delivery = request.headers.get("x-github-delivery", "")
    else:
        stamp = request.headers.get("x-slack-request-timestamp", "")
        if (
            len(stamp) > 12
            or not stamp.isdigit()
            or abs(time.time() - int(stamp)) > 300
        ):
            raise HTTPException(403, "Expired webhook")
        supplied = request.headers.get("x-slack-signature", "")
        expected = (
            "v0="
            + hmac.new(
                secret.get_secret_value().encode(),
                b"v0:" + stamp.encode() + b":" + payload,
                hashlib.sha256,
            ).hexdigest()
        )
        delivery = hashlib.sha256(payload).hexdigest()
    if (
        not hmac.compare_digest(supplied.encode(), expected.encode())
        or not delivery
        or len(delivery) > 160
    ):
        raise HTTPException(403, "Invalid webhook signature")
    try:
        data = json.loads(payload)
    except ValueError:
        raise HTTPException(400, "Invalid event") from None
    if not isinstance(data, dict):
        raise HTTPException(400, "Invalid event")
    if provider == "slack" and data.get("type") == "url_verification":
        return {"challenge": data.get("challenge")}
    accepted = db.scalar(
        insert(IntegrationEvent)
        .values(provider=provider, delivery_id=delivery)
        .on_conflict_do_nothing()
        .returning(IntegrationEvent.delivery_id)
    )
    if accepted is None:
        return {"duplicate": True}
    external = (
        str(data.get("installation", {}).get("id", ""))
        if provider == "github"
        else data.get("team_id", "")
    )
    rows = db.scalars(
        select(Connection)
        .where(
            Connection.provider == provider,
            Connection.external_id == external,
            Connection.status != "disconnected",
        )
        .with_for_update()
    ).all()
    event = data.get("event", {})
    removed = (
        provider == "github"
        and request.headers.get("x-github-event")
        in ("installation", "installation_repositories")
        and data.get("action") in ("deleted", "suspend", "removed")
        or provider == "slack"
        and event.get("type")
        in ("tokens_revoked", "app_uninstalled", "member_left_channel")
    )
    for row in rows:
        resource_id = (
            str(data.get("repository", {}).get("id", ""))
            if provider == "github"
            else event.get("channel", "")
        )
        if (
            not removed
            and resource_id
            and resource_id not in {item["id"] for item in row.selected_resources}
        ):
            continue
        if removed:
            service.hide_sources(db, row)
            row.status = "needs_reauthorization"
            row.next_sync_at = None
        elif row.selected_resources:
            if provider == "slack" and event.get("subtype") == "message_deleted":
                db.execute(
                    text("SELECT set_config('knotdevt.project_id', :project, true)"),
                    {"project": str(row.project_id)},
                )
                deleted = db.scalars(
                    select(Source).where(
                        Source.connection_id == row.id,
                        Source.external_object_id
                        == resource_id + ":" + str(event.get("deleted_ts", "")),
                    )
                ).all()
                for source in deleted:
                    source.deleted_at = datetime.now(UTC)
                    source.policy_revision += 1
            row.next_sync_at = datetime.now(UTC)
    db.commit()
    return {"accepted": True}
