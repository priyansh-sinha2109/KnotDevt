from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Receipt(Base):
    __tablename__ = "receipts"

    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("handover_versions.id"), primary_key=True
    )
    recipient_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"), primary_key=True, index=True
    )
    acknowledged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
