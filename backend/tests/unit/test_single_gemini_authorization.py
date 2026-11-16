from types import SimpleNamespace
from uuid import uuid4

from app.core.config import settings
from app.services.provider_authorization import authorized


def test_free_authorization_is_exact_job_model_and_one_attempt(monkeypatch):
    identity = uuid4()
    monkeypatch.setattr(settings(), "gemini_free_job_id", identity)
    job = SimpleNamespace(id=identity, queue="knotdevt-local-new", attempts=0)
    request = SimpleNamespace(
        provider="gemini",
        model="gemini-3.5-flash-lite",
        attempt_limit=1,
        token_limit=1500,
    )
    assert authorized(job, request)
    job.id = uuid4()
    assert not authorized(job, request)
    job.id = identity
    job.attempts = 1
    assert not authorized(job, request)
    job.attempts = 0
    request.model = "gemini-3.5-flash"
    assert not authorized(job, request)
    request.model = "gemini-3.5-flash-lite"
    request.attempt_limit = 2
    assert not authorized(job, request)
