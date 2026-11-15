"""Project-scoped encrypted tool connections, isolated from agent jobs."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision = "0011_integrations"
down_revision = "0010_chatbot_guide"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integration_connections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "project_id", sa.Uuid(), sa.ForeignKey("projects.id"), nullable=False
        ),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("external_id", sa.String(160), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("credential", sa.Text()),
        sa.Column("scopes", postgresql.JSONB(), nullable=False),
        sa.Column("selected_resources", postgresql.JSONB(), nullable=False),
        sa.Column("cursor", postgresql.JSONB(), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True)),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("next_sync_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.String(200)),
        sa.Column("imported_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_integration_connections_project_id",
        "integration_connections",
        ["project_id"],
    )


def downgrade() -> None:
    op.drop_table("integration_connections")
