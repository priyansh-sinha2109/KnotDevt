from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session

from app.core.config import settings


class Base(DeclarativeBase):
    pass


def connect(url: str) -> Engine:
    db_engine = create_engine(
        url,
        pool_pre_ping=True,
        pool_timeout=3,
        # Neon/PgBouncer transaction pooling can reuse a connection whose
        # server-side prepared statements belong to a different session.
        # psycopg then raises ProgrammingError on otherwise valid requests.
        # Disabling preparation keeps pooled hosted sessions deterministic.
        connect_args={
            "connect_timeout": 3,
            "prepare_threshold": None,
        },
        hide_parameters=True,
    )
    @event.listens_for(db_engine, "connect")
    def _set_search_path(dbapi_connection, _connection_record) -> None:
        previous_autocommit = dbapi_connection.autocommit
        dbapi_connection.autocommit = True
        try:
            with dbapi_connection.cursor() as cursor:
                cursor.execute("SET SESSION search_path TO public, agent_checkpoints")
        finally:
            dbapi_connection.autocommit = previous_autocommit

    return db_engine


@lru_cache
def engine() -> Engine:
    return connect(settings().runtime_database_url.get_secret_value())


@lru_cache
def migration_engine() -> Engine:
    return connect(settings().database_url.get_secret_value())


def database() -> Iterator[Session]:
    with Session(engine(), expire_on_commit=False) as session:
        yield session
