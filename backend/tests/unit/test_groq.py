import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from pydantic import BaseModel, SecretStr

from app.agents import provider
from app.agents.graph import RunConfig, failure_diagnostic, stage_error
from app.schemas.agents import ContextBundle, ContextItem, DecisionOutput


class Output(BaseModel):
    feedback: str


def _settings():
    return SimpleNamespace(
        groq_api_key=SecretStr("synthetic-only"),
        groq_model="openai/gpt-oss-20b",
        groq_min_interval_seconds=0,
        groq_max_retries=1,
        groq_self_service_since=None,
    )


def _context() -> ContextBundle:
    return ContextBundle(
        task="Prepare a safe handover",
        evidence=[
            ContextItem(
                revision_id=UUID("00000000-0000-0000-0000-000000000001"),
                source_id="PR-1",
                event_type="pull_request",
                excerpt="The release decision is proposed pending QA.",
                event_time="2026-11-16T00:00:00Z",
                related_ids=[],
            )
        ],
    )


def test_groq_uses_openai_compatible_strict_schema(monkeypatch):
    client = MagicMock()
    client.__enter__.return_value = client
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content='{"feedback":"grounded"}'))
        ]
    )
    constructor = MagicMock(return_value=client)
    monkeypatch.setattr("openai.OpenAI", constructor)
    monkeypatch.setattr(provider, "settings", _settings)

    result = provider.generate(
        "readiness_coach",
        Output(feedback="input"),
        Output,
        "openai/gpt-oss-20b",
        10,
        900,
        provider_name="groq",
    )

    assert result.feedback == "grounded"
    assert constructor.call_args.kwargs["base_url"] == "https://api.groq.com/openai/v1"
    request = client.chat.completions.create.call_args.kwargs
    assert request["max_tokens"] == 900
    assert request["response_format"]["type"] == "json_schema"
    assert request["response_format"]["json_schema"]["strict"] is True


def test_groq_falls_back_to_json_object_only_for_schema_rejection(monkeypatch):
    client = MagicMock()
    client.__enter__.return_value = client
    error = __import__("openai").APIStatusError(
        "response_format unsupported", response=MagicMock(status_code=400), body=None
    )
    client.chat.completions.create.side_effect = [
        error,
        SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content='{"feedback":"ok"}'))
            ]
        ),
    ]
    monkeypatch.setattr("openai.OpenAI", MagicMock(return_value=client))
    monkeypatch.setattr(provider, "settings", _settings)
    provider._reset_request_telemetry()

    result = provider.generate_groq(
        "readiness_coach",
        Output(feedback="input"),
        Output,
        "openai/gpt-oss-20b",
        10,
        900,
    )
    assert result.feedback == "ok"
    assert client.chat.completions.create.call_args_list[1].kwargs[
        "response_format"
    ] == {"type": "json_object"}
    assert provider.request_telemetry()["provider_attempts"] == 2
    assert provider.request_telemetry()["fallback_attempts"] == 1


def test_groq_invalid_output_never_becomes_success(monkeypatch):
    client = MagicMock()
    client.__enter__.return_value = client
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))]
    )
    monkeypatch.setattr("openai.OpenAI", MagicMock(return_value=client))
    monkeypatch.setattr(provider, "settings", _settings)

    with pytest.raises(provider.ProviderOutputError):
        provider.generate_groq(
            "readiness_coach",
            Output(feedback="input"),
            Output,
            "openai/gpt-oss-20b",
            10,
            900,
        )


def test_groq_extraction_literal_json_example_does_not_become_prompt_variable(
    monkeypatch,
):
    client = MagicMock()
    client.__enter__.return_value = client
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"findings":[]}'))]
    )
    monkeypatch.setattr("openai.OpenAI", MagicMock(return_value=client))
    monkeypatch.setattr(provider, "settings", _settings)

    result = provider.generate(
        "decision_analyst",
        _context(),
        DecisionOutput,
        "openai/gpt-oss-20b",
        10,
        900,
        provider_name="groq",
    )

    assert result.claims == []
    request = client.chat.completions.create.call_args.kwargs
    assert request["response_format"] == {"type": "json_object"}
    assert provider.request_telemetry()["external_request_attempted"] is True
    assert provider.request_telemetry()["provider_attempts"] == 1


def test_failure_diagnostic_identifies_pre_request_prompt_error_without_content():
    provider._reset_request_telemetry()
    cfg = RunConfig(
        job_id=UUID("00000000-0000-0000-0000-000000000002"),
        provider="groq",
        model="openai/gpt-oss-20b",
        attempts=1,
        timeout=25,
        token_limit=900,
    )
    try:
        raise KeyError("missing prompt variable")
    except KeyError as exc:
        diagnostic = failure_diagnostic(exc, cfg, "decision_analyst", cfg.model)
        code = stage_error(exc)

    assert code == ("stage_failed", True)
    assert diagnostic["exception_class"] == "KeyError"
    assert diagnostic["external_request_attempted"] is False
    assert diagnostic["provider_attempts"] == 0
    assert "missing prompt variable" not in str(diagnostic)
    assert isinstance(diagnostic["worker_code_fingerprint"], str)


def test_failure_diagnostic_unwraps_parallel_group_and_preserves_http_metadata():
    response = MagicMock(status_code=400, headers={"x-request-id": "req-safe"})
    provider_error = __import__("openai").APIStatusError(
        "redacted",
        response=response,
        body={"type": "invalid_request_error", "code": "bad_schema"},
    )
    cfg = RunConfig(
        job_id=UUID("00000000-0000-0000-0000-000000000003"),
        provider="groq",
        model="openai/gpt-oss-20b",
        attempts=1,
        timeout=25,
        token_limit=900,
    )
    diagnostic = failure_diagnostic(
        BaseExceptionGroup("parallel", [asyncio.CancelledError(), provider_error]),
        cfg,
        "decision_analyst",
        cfg.model,
    )

    assert stage_error(provider_error) == ("provider_invalid_request", False)
    assert diagnostic["parallel_exception_group"] is True
    assert diagnostic["provider_http_status"] == 400
    assert diagnostic["provider_error_type"] == "invalid_request_error"
    assert diagnostic["provider_error_code"] == "bad_schema"
    assert diagnostic["provider_request_id"] == "req-safe"


def test_collateral_parallel_cancellation_is_not_reported_as_primary_failure():
    assert stage_error(provider.ParallelStageCancelledError("peer failed")) == (
        "parallel_stage_cancelled",
        False,
    )
    assert stage_error(provider.InferenceBudgetExceededError("budget")) == (
        "inference_budget_exhausted",
        False,
    )
