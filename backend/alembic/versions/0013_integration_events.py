"""Transactional webhook deduplication, without retaining event secrets/payloads."""

import sqlalchemy as sa

from alembic import op

revision = "0013_integration_events"
down_revision = "0012_source_origins"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integration_events",
        sa.Column("provider", sa.String(16), primary_key=True),
        sa.Column("delivery_id", sa.String(160), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("integration_events")
