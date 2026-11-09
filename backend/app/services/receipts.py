from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.receipts import Receipt
from app.repositories.sources import lock_project
from app.schemas.receipts import ReceiptView
from app.services.access import audit
from app.services.versions import version_access, version_state


def receipt_view(record: Receipt) -> ReceiptView:
    return ReceiptView(
        version_id=record.version_id,
        recipient_id=record.recipient_id,
        acknowledged_at=record.acknowledged_at,
    )


def acknowledge(
    db: Session,
    version_id: UUID,
    user_id: UUID,
) -> tuple[ReceiptView, bool]:
    version, _ = version_access(db, version_id, user_id, assigned_only=True)
    lock_project(db, version.project_id)
    version, access = version_access(db, version_id, user_id, assigned_only=True)
    state = version_state(db, version, user_id)
    if state in {"unavailable", "withdrawn"}:
        raise HTTPException(409, "Handover is unavailable")
    existing = db.get(Receipt, (version_id, user_id))
    if existing is not None:
        return receipt_view(existing), False
    if state != "approved":
        raise HTTPException(409, "Handover requires review")
    record = Receipt(version_id=version_id, recipient_id=user_id)
    db.add(record)
    audit(
        db, user_id, "handover.received", project=access.project, target_id=version_id
    )
    db.flush()
    result = receipt_view(record)
    db.commit()
    return result, True


def read_receipt(db: Session, version_id: UUID, user_id: UUID) -> ReceiptView:
    version, _ = version_access(db, version_id, user_id, assigned_only=True)
    if version_state(db, version, user_id) in {"unavailable", "withdrawn"}:
        raise HTTPException(409, "Handover is unavailable")
    record = db.get(Receipt, (version_id, user_id))
    if record is None:
        raise HTTPException(404, "Receipt not found")
    return receipt_view(record)
