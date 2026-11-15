"""Connector provenance on existing sources, preserving all old records."""

import sqlalchemy as sa
from alembic import op

revision = "0012_source_origins"
down_revision = "0011_integrations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sources", sa.Column("connection_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "sources_connection_id_fkey",
        "sources",
        "integration_connections",
        ["connection_id"],
        ["id"],
    )
    op.add_column(
        "sources", sa.Column("external_resource_id", sa.String(160), nullable=True)
    )
    op.add_column(
        "sources", sa.Column("external_object_id", sa.String(300), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("sources", "external_object_id")
    op.drop_column("sources", "external_resource_id")
    op.drop_constraint("sources_connection_id_fkey", "sources", type_="foreignkey")
    op.drop_column("sources", "connection_id")
