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
    llm_provider: Literal["fake", "gemini", "openai", "openrouter", "groq"] = "fake"
    llm_model: str = Field(default="gemini-3.8-flash", min_length=1, max_length=128)
    gemini_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    openrouter_api_key: SecretStr | None = None
    openrouter_model: str = Field(
        default="openrouter/free", min_length=1, max_length=128
    )
    groq_api_key: SecretStr | None = None
    groq_model: str = Field(
        default="openai/gpt-oss-20b", min_length=1, max_length=128
    )
    groq_min_interval_seconds: float = Field(default=1.0, ge=0, le=60)
    groq_max_retries: int = Field(default=1, ge=0, le=2)
    tavily_api_key: SecretStr | None = None
    integration_encryption_key: SecretStr | None = None
    integration_callback_base: str = "http://localhost:8080/api/v1/integrations"
    frontend_url: str = "http://localhost:3000"
    github_client_id: str = ""
    github_client_secret: SecretStr | None = None
    slack_client_id: str = ""
    slack_client_secret: SecretStr | None = None
    slack_signing_secret: SecretStr | None = None
    jira_client_id: str = ""
    jira_client_secret: SecretStr | None = None
    github_webhook_secret: SecretStr | None = None
    public_research_enabled: bool = False
    openai_model: str = Field(default="gpt-4o-mini", min_length=1, max_length=128)
    agent_attempts: int = Field(default=2, ge=1, le=3)
    agent_timeout_seconds: int = Field(default=25, ge=3, le=60)
    agent_token_limit: int = Field(default=3000, ge=300, le=6000)
    redis_url: SecretStr = SecretStr("redis://127.0.0.1:56379/0")
    job_queue: str = Field(default="celery", pattern=r"^[A-Za-z0-9_.-]{1,100}$")
    import_job_queue: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9_.-]{1,100}$"
    )
    live_ai_authorized: bool = False
    # Provider-scoped administrator switch. This never authorizes other live providers.
    groq_free_authorized: bool = False
    groq_free_daily_request_limit: int = Field(default=1000, ge=1, le=10000)
    groq_free_daily_token_limit: int = Field(default=200000, ge=1000, le=1000000)
    gemini_free_job_id: UUID | None = None
    openrouter_free_job_id: UUID | None = None
    groq_free_job_id: UUID | None = None
    groq_authorized_queue: str = Field(default="knotdevt-groq-production", pattern=r"^[A-Za-z0-9_.-]{1,100}$")
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
