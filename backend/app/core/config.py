from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    database_url: SecretStr
    session_signing_secret: SecretStr = Field(min_length=32)
    secure_cookies: bool = False
    redis_url: SecretStr = SecretStr("redis://127.0.0.1:56379/0")
    allowed_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
