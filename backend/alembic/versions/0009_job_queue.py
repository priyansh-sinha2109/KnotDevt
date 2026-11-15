"""Queue assignment for new jobs; historical rows remain unassigned."""

import sqlalchemy as sa

from alembic import op

revision = "0009_job_queue"
down_revision = "0008_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("queue", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "queue")
