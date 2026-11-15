"""Free-text Gemini chat generation for the guide chatbot.

This module is deliberately separate from ``app.agents.provider`` (the
five-agent structured-output adapter) and from the LangGraph workflow.  It
performs a single bounded ``generate_content`` call with a conversation history
and returns plain text — no structured JSON schema, no citations, no agent
stages.

Safety and budget rules:
- Only the Gemini provider is used; no silent fallback to OpenAI, OpenRouter,
  or deterministic models.
- Requests are bounded by ``timeout_seconds`` and ``token_limit``.
- Retries are disabled (``attempts=1``); the caller decides whether to retry.
- HTTP 400/401/403/429/5xx and timeouts surface as typed exceptions.
- When the free-tier quota is exhausted the caller must stop, not loop.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.core.config import settings

logger = logging.getLogger(__name__)


class ChatProviderError(Exception):
    """Base error for chatbot provider failures."""


class ChatQuotaExhausted(ChatProviderError):
    """Gemini free-tier quota is exhausted — do not retry."""


class ChatAuthFailed(ChatProviderError):
    """Gemini API key is invalid or unauthorized (401/403)."""


class ChatModelUnavailable(ChatProviderError):
    """The configured model does not exist or is unavailable (404)."""


class ChatInvalidRequest(ChatProviderError):
    """The request was rejected by Gemini (400)."""


class ChatTemporarilyUnavailable(ChatProviderError):
    """Gemini returned a 5xx or timed out — a retry may help."""


class ChatCredentialUnavailable(ChatProviderError):
    """No Gemini API key is configured."""


@dataclass(frozen=True)
class ChatTurn:
    """One turn in the conversation history."""

    role: Literal["user", "model"]
    content: str


def _map_error(error: genai_errors.APIError) -> ChatProviderError:
    code = error.code
    if code == 429:
        return ChatQuotaExhausted("Gemini free-tier quota exhausted")
    if code in (401, 403):
        return ChatAuthFailed("Gemini authentication failed")
    if code == 404:
        return ChatModelUnavailable("The configured Gemini model is unavailable")
    if code == 400:
        return ChatInvalidRequest("Gemini rejected the request")
    if code in (500, 502, 503, 504):
        return ChatTemporarilyUnavailable("Gemini is temporarily unavailable")
    return ChatProviderError(f"Gemini request failed (HTTP {code})")


def generate_chat(
    system_instruction: str,
    history: list[ChatTurn],
    *,
    model: str | None = None,
    timeout_seconds: int | None = None,
    token_limit: int | None = None,
) -> str:
    """Send one bounded free-text Gemini call and return the assistant text.

    ``system_instruction`` is the full system prompt (boundary + knowledge +
    page context).  ``history`` is the prior conversation turns (most recent
    last).  Returns plain text; never raises on empty output (returns "").
    Raises a typed ``ChatProviderError`` subclass on any failure.
    """
    cfg = settings()
    credential = cfg.gemini_api_key
    if credential is None or not credential.get_secret_value().strip():
        raise ChatCredentialUnavailable("Gemini credential is unavailable")

    selected_model = model or cfg.llm_model
    selected_timeout = timeout_seconds or cfg.agent_timeout_seconds
    selected_tokens = token_limit or min(cfg.agent_token_limit, 1200)

    # Build Gemini Content list from the conversation history.
    contents: list[types.Content] = []
    for turn in history:
        role = "user" if turn.role == "user" else "model"
        contents.append(
            types.Content(
                role=role,
                parts=[types.Part.from_text(text=turn.content)],
            )
        )

    try:
        with genai.Client(
            api_key=credential.get_secret_value(),
            http_options=types.HttpOptions(
                timeout=selected_timeout * 1000,
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        ) as client:
            response = client.models.generate_content(
                model=selected_model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    max_output_tokens=selected_tokens,
                    temperature=0.2,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(
                        disable=True
                    ),
                ),
            )
    except genai_errors.APIError as error:
        mapped = _map_error(error)
        logger.warning(
            "chatbot_gemini_error code=%s mapped=%s",
            error.code,
            type(mapped).__name__,
        )
        raise mapped from error
    except TimeoutError as error:
        logger.warning("chatbot_gemini_timeout")
        raise ChatTemporarilyUnavailable("Gemini request timed out") from error

    text = response.text or ""
    if not text.strip():
        # An empty but successful response is not a simulated answer; surface it.
        raise ChatProviderError("Gemini returned no content")
    return text
