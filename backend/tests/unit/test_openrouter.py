from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel, SecretStr

from app.agents import provider


class Output(BaseModel):
    feedback: str


def test_openrouter_free_structured_request(monkeypatch):
    client = MagicMock()
    client.__enter__.return_value = client
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content='{"feedback":"Review evidence"}')
            )
        ]
    )
    constructor = MagicMock(return_value=client)
    monkeypatch.setattr("openai.OpenAI", constructor)
    monkeypatch.setattr(
        provider,
        "settings",
        lambda: SimpleNamespace(openrouter_api_key=SecretStr("synthetic-only")),
    )
    result = provider.generate(
        "readiness_coach",
        Output(feedback="Input"),
        Output,
        "openrouter/free",
        10,
        1500,
        provider_name="openrouter",
    )
    assert result.feedback == "Review evidence"
    assert constructor.call_args.kwargs["base_url"] == "https://openrouter.ai/api/v1"
    assert constructor.call_args.kwargs["max_retries"] == 0
    request = client.chat.completions.create.call_args.kwargs
    assert request["max_tokens"] == 1500
    assert request["response_format"]["type"] == "json_schema"
    assert request["extra_body"]["provider"] == {
        "require_parameters": True,
        "allow_fallbacks": False,
        "max_price": {"prompt": 0, "completion": 0},
        "data_collection": "deny",
    }


def test_openrouter_rejects_paid_model_before_network():
    with pytest.raises(ValueError, match="free model"):
        provider.generate_openrouter(
            "readiness_coach",
            Output(feedback="Input"),
            Output,
            "openai/gpt-4o",
            10,
            1500,
        )


def test_openrouter_invalid_output_is_not_success(monkeypatch):
    client = MagicMock()
    client.__enter__.return_value = client
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))]
    )
    monkeypatch.setattr("openai.OpenAI", MagicMock(return_value=client))
    monkeypatch.setattr(
        provider,
        "settings",
        lambda: SimpleNamespace(openrouter_api_key=SecretStr("synthetic-only")),
    )
    with pytest.raises(provider.ProviderOutputError):
        provider.generate_openrouter(
            "readiness_coach",
            Output(feedback="Input"),
            Output,
            "openrouter/free",
            10,
            1500,
        )


def test_openrouter_authorization_is_one_job(monkeypatch):
    from uuid import uuid4
    from app.core.config import settings
    from app.services.provider_authorization import authorized

    identity = uuid4()
    monkeypatch.setattr(settings(), "openrouter_free_job_id", identity)
    monkeypatch.setattr(settings(), "live_ai_authorized", False)
    job = SimpleNamespace(id=identity, queue="knotdevt-local-new", attempts=0)
    request = SimpleNamespace(
        provider="openrouter",
        model="openrouter/free",
        attempt_limit=1,
        token_limit=1500,
    )
    assert authorized(job, request)
    request.provider = "gemini"
    assert not authorized(job, request)
    request.provider = "openrouter"
    job.id = uuid4()
    assert not authorized(job, request)
    job.id = identity
    request.model = "openai/gpt-4o"
    assert not authorized(job, request)
