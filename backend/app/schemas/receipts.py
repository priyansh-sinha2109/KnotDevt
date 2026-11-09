from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ReceiptView(BaseModel):
    version_id: UUID
    recipient_id: UUID
    acknowledged_at: datetime
