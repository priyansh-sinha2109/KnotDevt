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
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
