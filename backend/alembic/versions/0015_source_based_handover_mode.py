"""Add explicit draft mode for deterministic source handovers."""

import sqlalchemy as sa

from alembic import op

revision = "0015_source_based_handover_mode"
down_revision = "0014_agent_run_diagnostics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "handover_drafts",
        sa.Column(
            "mode", sa.String(length=24), server_default="ai_assisted", nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_column("handover_drafts", "mode")
