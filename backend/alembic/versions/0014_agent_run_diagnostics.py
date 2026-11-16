"""Persist sanitized agent-stage failure diagnostics."""

import sqlalchemy as sa

from alembic import op

revision = "0014_agent_run_diagnostics"
down_revision = "0013_integration_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("diagnostic", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_runs", "diagnostic")
