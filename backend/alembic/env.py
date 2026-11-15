from alembic import context
from app.core.config import settings
from app.db import registry  # noqa: F401
from app.db.session import Base, migration_engine

if context.is_offline_mode():
    context.configure(
        url=settings().database_url.get_secret_value(),
        target_metadata=Base.metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    with migration_engine().connect() as connection:
        # LangGraph owns these tables and its own migrations. They are visible
        # through the application search_path but must never be dropped by
        # application autogeneration. Keep checking all other tables for drift.
        context.configure(
            connection=connection,
            target_metadata=Base.metadata,
            include_name=lambda name, type_, parent_names: (
                not (
                    type_ == "table"
                    and name
                    in {
                        "checkpoints",
                        "checkpoint_blobs",
                        "checkpoint_writes",
                        "checkpoint_migrations",
                    }
                )
            ),
        )
        with context.begin_transaction():
            context.run_migrations()
