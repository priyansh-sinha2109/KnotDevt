"""Dedicated connector-only queue. Never registers or consumes AI task names."""

import random
from datetime import UTC, datetime, timedelta
from uuid import UUID

from celery import Celery  # type: ignore[import-untyped]
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import registry  # noqa: F401
from app.db.integrations import Connection
from app.db.session import engine
from app.integrations.providers import RemoteError
from app.services import integrations

celery = Celery("knotdevt-connectors", broker=settings().redis_url.get_secret_value())
celery.conf.update(
    task_default_queue="knotdevt-connectors",
    task_ignore_result=True,
    task_serializer="json",
    accept_content=["json"],
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    beat_schedule={
        "recover-connector-syncs": {
            "task": "knotdevt.connectors.dispatch",
            "schedule": 15.0,
        }
    },
)


def sync(connection_id: str) -> None:
    with Session(engine()) as db, db.begin():
        row = db.scalar(
            select(Connection)
            .where(Connection.id == UUID(connection_id))
            .with_for_update(skip_locked=True)
        )
        if (
            row is None
            or not row.credential
            or not row.selected_resources
            or row.status
            in {"disconnected", "permission_denied", "needs_reauthorization"}
        ):
            return
        if not row.next_sync_at or row.next_sync_at > datetime.now(UTC):
            return
        row.last_attempt_at = datetime.now(UTC)
        # This internal scope survives a failed page savepoint, allowing retained
        # evidence to be hidden when external or KnotDevt access is revoked.
        db.execute(
            text("SELECT set_config('knotdevt.project_id', :project, true)"),
            {"project": str(row.project_id)},
        )
        try:
            with db.begin_nested():
                integrations.sync_page(db, row)
        except RemoteError as error:
            failures = int(row.cursor.get("failures", 0)) + 1
            row.cursor = {**row.cursor, "failures": failures}
            row.status, row.last_error = error.status, error.message
            row.next_sync_at = (
                datetime.now(UTC)
                + timedelta(
                    seconds=max(error.delay, min(3600, 60 * 2 ** (failures - 1)))
                    + random.randint(1, 15)
                )
                if error.status in {"rate_limited", "sync_failed"} and failures < 6
                else None
            )
            if error.status in {"permission_denied", "needs_reauthorization"}:
                integrations.hide_sources(db, row)
        except HTTPException:
            row.status = "permission_denied"
            row.last_error = "Project access changed. Reauthorization is required."
            row.next_sync_at = None
            integrations.hide_sources(db, row)
        except Exception:
            row.status, row.last_error = (
                "sync_failed",
                "Sync could not complete. Check configuration and retry.",
            )
            row.next_sync_at = None


def dispatch() -> None:
    with Session(engine()) as db:
        ids = db.scalars(
            select(Connection.id)
            .where(
                Connection.next_sync_at <= datetime.now(UTC),
                Connection.status.not_in(
                    ("disconnected", "needs_reauthorization", "permission_denied")
                ),
            )
            .limit(20)
        ).all()
        for value in ids:
            celery.send_task(
                "knotdevt.connectors.sync",
                args=[str(value)],
                queue="knotdevt-connectors",
                retry=False,
            )


celery.task(name="knotdevt.connectors.sync")(sync)
celery.task(name="knotdevt.connectors.dispatch")(dispatch)
