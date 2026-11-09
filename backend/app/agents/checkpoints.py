from collections.abc import Iterator
from contextlib import contextmanager

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg import Connection
from psycopg.rows import dict_row
from sqlalchemy import make_url

from app.core.config import settings


@contextmanager
def checkpoints() -> Iterator[PostgresSaver]:
    url = make_url(settings().runtime_database_url.get_secret_value())
    dsn = url.set(drivername="postgresql").render_as_string(hide_password=False)
    with Connection.connect(
        dsn,
        autocommit=True,
        row_factory=dict_row,
        prepare_threshold=0,
        connect_timeout=3,
    ) as connection:
        connection.execute("SET search_path TO agent_checkpoints")
        yield PostgresSaver(connection)
