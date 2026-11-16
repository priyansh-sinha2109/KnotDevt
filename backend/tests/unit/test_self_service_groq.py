from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.agents.provider import InferenceBudgetExceededError, reserve_groq_budget
from app.core.config import settings
from app.services.provider_authorization import authorized


def test_new_jobs_authorized_but_history_and_other_providers_blocked(monkeypatch):
    cutoff = datetime.now(UTC)
    monkeypatch.setattr(settings(), "groq_self_service_since", cutoff)
    monkeypatch.setattr(settings(), "live_ai_authorized", False)
    monkeypatch.setattr(settings(), "groq_free_authorized", False)
    job = SimpleNamespace(created_at=cutoff, queue=settings().job_queue, attempts=0)
    request = SimpleNamespace(
        provider="groq", model=settings().groq_model, attempt_limit=1, token_limit=1500
    )
    assert authorized(job, request)
    job.created_at = cutoff - timedelta(seconds=1)
    assert not authorized(job, request)
    job.created_at = cutoff
    request.token_limit = 6000
    assert not authorized(job, request)


def test_exhausted_shared_budget_stops_before_inference(monkeypatch):
    monkeypatch.setattr(settings(), "groq_self_service_since", datetime.now(UTC))
    monkeypatch.setattr(
        "app.core.cache.redis_client", lambda: SimpleNamespace(eval=lambda *args: 0)
    )
    with pytest.raises(InferenceBudgetExceededError):
        reserve_groq_budget(1000, 1500)


def test_missing_groq_key_is_configuration_error_before_request(monkeypatch):
    from app.agents.graph import stage_error
    from app.agents.provider import ProviderConfigurationError, generate_groq
    from app.schemas.agents import WorkOutput

    monkeypatch.setattr(settings(), "groq_api_key", None)
    with pytest.raises(ProviderConfigurationError) as error:
        generate_groq(
            "work_mapper",
            WorkOutput(claims=[], recurring_problem_candidates=[], relationships=[]),
            WorkOutput,
            settings().groq_model,
            30,
            1500,
        )
    assert stage_error(error.value) == ("provider_configuration_error", False)
