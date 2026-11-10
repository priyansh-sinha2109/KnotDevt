from google.genai import errors

from app.agents.graph import stage_error


def test_provider_errors_are_sanitized_and_quota_is_not_retried() -> None:
    assert stage_error(errors.ClientError(429, {})) == (
        "provider_quota_or_rate_limit",
        False,
    )
    assert stage_error(errors.ClientError(401, {})) == (
        "provider_authentication_failed",
        False,
    )
    assert stage_error(errors.ClientError(404, {})) == (
        "provider_model_unavailable",
        False,
    )
    assert stage_error(errors.ClientError(400, {})) == (
        "provider_invalid_request",
        False,
    )
    assert stage_error(errors.ServerError(503, {})) == (
        "provider_temporarily_unavailable",
        True,
    )


def test_invalid_output_gets_one_bounded_retry() -> None:
    assert stage_error(ValueError("schema mismatch")) == ("invalid_output", True)
