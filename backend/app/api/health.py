from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.session import engine

router = APIRouter(tags=["health"])


class Health(BaseModel):
    status: Literal["ok"] = "ok"


class Readiness(BaseModel):
    status: Literal["ready", "unavailable"]
    postgres: bool
    redis: bool


@lru_cache
def redis_client() -> Redis:
    return Redis.from_url(
        settings().redis_url.get_secret_value(),
        socket_connect_timeout=2,
        socket_timeout=2,
    )


@router.get("/health")
def health() -> Health:
    return Health()


@router.get("/health/ready", responses={503: {"model": Readiness}})
def ready(response: Response) -> Readiness:
    try:
        with engine().connect() as conn:
            postgres = bool(
                conn.scalar(text("SELECT to_regclass('workspaces') IS NOT NULL"))
            )
    except SQLAlchemyError:
        postgres = False

    try:
        redis = bool(redis_client().ping())
    except RedisError:
        redis = False

    if not (postgres and redis):
        response.status_code = 503
        return Readiness(status="unavailable", postgres=postgres, redis=redis)
    return Readiness(status="ready", postgres=True, redis=True)
