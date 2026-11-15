from functools import lru_cache
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    database_url: SecretStr
    runtime_database_url: SecretStr
    session_signing_secret: SecretStr = Field(min_length=32)
    secure_cookies: bool = False
    session_cookie_samesite: Literal["lax", "none"] = "lax"
    llm_provider: Literal["fake", "gemini", "openai", "openrouter"] = "fake"
    llm_model: str = Field(default="gemini-3.8-flash", min_length=1, max_length=128)
    gemini_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    openrouter_api_key: SecretStr | None = None
    openrouter_model: str = Field(
        default="openrouter/free", min_length=1, max_length=128
    )
    tavily_api_key: SecretStr | None = None
    public_research_enabled: bool = False
    openai_model: str = Field(default="gpt-4o-mini", min_length=1, max_length=128)
    agent_attempts: int = Field(default=2, ge=1, le=3)
    agent_timeout_seconds: int = Field(default=25, ge=3, le=60)
    agent_token_limit: int = Field(default=3000, ge=300, le=6000)
    redis_url: SecretStr = SecretStr("redis://127.0.0.1:56379/0")
    job_queue: str = Field(default="celery", pattern=r"^[A-Za-z0-9_.-]{1,100}$")
    live_ai_authorized: bool = False
    gemini_free_job_id: UUID | None = None
    openrouter_free_job_id: UUID | None = None
    allowed_origins: list[str] = ["http://localhost:3000"]

    @model_validator(mode="after")
    def secure_cross_site_cookie(self) -> "Settings":
        if self.session_cookie_samesite == "none" and not self.secure_cookies:
            raise ValueError(
                "SESSION_COOKIE_SAMESITE=none requires SECURE_COOKIES=true"
            )
        return self


@lru_cache
def settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
