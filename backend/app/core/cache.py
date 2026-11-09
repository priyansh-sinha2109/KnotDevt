from functools import lru_cache

from redis import Redis

from app.core.config import settings


@lru_cache
def redis_client() -> Redis:
    return Redis.from_url(
        settings().redis_url.get_secret_value(),
        socket_connect_timeout=2,
        socket_timeout=2,
    )
