from uuid import UUID

from fastapi import APIRouter, Response

from app.api.dependencies import DB, Actor
from app.schemas.receipts import ReceiptView
from app.services.receipts import acknowledge, read_receipt

router = APIRouter(tags=["receipt"])


@router.post(
    "/versions/{version_id}/receipt",
    status_code=201,
    responses={200: {"model": ReceiptView}},
)
def receipt_create(
    version_id: UUID, response: Response, identity: Actor, db: DB
) -> ReceiptView:
    result, created = acknowledge(db, version_id, identity.user.id)
    if not created:
        response.status_code = 200
    return result


@router.get("/versions/{version_id}/receipt")
def receipt_get(version_id: UUID, identity: Actor, db: DB) -> ReceiptView:
    return read_receipt(db, version_id, identity.user.id)
