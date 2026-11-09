from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session

from app.core.config import settings


class Base(DeclarativeBase):
    pass


@lru_cache
def engine() -> Engine:
    return create_engine(
        settings().database_url.get_secret_value(),
        pool_pre_ping=True,
        pool_timeout=3,
        connect_args={"connect_timeout": 3},
        hide_parameters=True,
    )


def database() -> Iterator[Session]:
    with Session(engine()) as session:
        yield session
