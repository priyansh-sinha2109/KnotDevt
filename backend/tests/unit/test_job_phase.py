from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from app.services.jobs import job_view


def job(*, state: str, kind: str = "import", attempts: int = 0) -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid4(),
        project_id=uuid4(),
        kind=kind,
        state=state,
        attempts=attempts,
        dispatch_after=now + timedelta(seconds=15),
        created_at=now,
        error_code="temporary_provider_error" if attempts else None,
    )


def test_job_phase_exposes_bounded_retry_without_changing_persisted_state() -> None:
    view = job_view(job(state="queued", attempts=1))

    assert view.state == "queued"
    assert view.phase == "waiting_retry"
    assert view.next_action == "wait"
    assert view.attempt_count == 1
    assert view.next_retry_at is not None


def test_agent_success_is_a_human_review_checkpoint() -> None:
    view = job_view(job(state="succeeded", kind="agents", attempts=1))

    assert view.state == "succeeded"
    assert view.phase == "awaiting_human_review"
    assert view.next_action == "review"
    assert view.next_retry_at is None


def test_terminal_job_phases_have_unambiguous_next_actions() -> None:
    completed = job_view(job(state="succeeded", attempts=1))
    failed = job_view(job(state="failed", attempts=2))

    assert (completed.phase, completed.next_action) == ("succeeded", "none")
    assert (failed.phase, failed.next_action) == ("failed", "inspect_error")
