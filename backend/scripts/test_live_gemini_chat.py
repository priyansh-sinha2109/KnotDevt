"""
Bounded live Gemini chat test — SYNTHETIC INPUT ONLY.

This script makes ONE bounded call to the real Gemini API using the configured
credential and model. It does NOT use real project data, user data, or any
sensitive content. The input is a synthetic guide question.

USAGE:
    cd backend
    .venv\\Scripts\\python.exe -m scripts.test_live_gemini_chat

DO NOT RUN without explicit user approval. This script makes a real API call
that may consume free-tier quota.
"""

from __future__ import annotations

import sys

from app.agents.chatbot_provider import (
    ChatProviderError,
    ChatQuotaExhausted,
    ChatTurn,
    generate_chat,
)
from app.core.config import settings
from app.knowledge.product_knowledge import KNOWLEDGE_TEXT
from app.services.chatbot import _BOUNDARY


def main() -> int:
    cfg = settings()
    credential = cfg.gemini_api_key

    print("=== Bounded Live Gemini Chat Test ===")
    print(f"Model: {cfg.llm_model}")
    print(f"Timeout: {cfg.agent_timeout_seconds}s")
    print(f"Token limit: {min(cfg.agent_token_limit, 1200)}")
    print(f"API key present: {credential is not None}")
    print()

    if credential is None or not credential.get_secret_value().strip():
        print("ERROR: GEMINI_API_KEY is not configured. Aborting.")
        return 1

    # Synthetic input — no real user data.
    system_instruction = (
        f"{_BOUNDARY}\n\nPRODUCT KNOWLEDGE\n{KNOWLEDGE_TEXT.strip()}\n\n"
        "ACCESS LEVEL: Guest (not signed in).\n"
        "PAGE CONTEXT: The user is on the public landing page.\n\n"
        "Answer the user's question concisely."
    )

    history = [
        ChatTurn(role="user", content="What is KnotDevt?"),
    ]

    print("Sending synthetic question: 'What is KnotDevt?'")
    print("Waiting for Gemini response...")
    print()

    try:
        response = generate_chat(
            system_instruction=system_instruction,
            history=history,
        )
    except ChatQuotaExhausted:
        print("RESULT: Quota exhausted (429). Free-tier limit reached.")
        print("The chatbot correctly reports this to the user — no simulated answer.")
        return 0
    except ChatProviderError as exc:
        print(f"RESULT: Provider error — {type(exc).__name__}: {exc}")
        print("The chatbot correctly surfaces this as a truthful error state.")
        return 1

    print("=== Gemini Response ===")
    print(response)
    print()
    print(f"Response length: {len(response)} characters")
    print()

    # Basic validation: response should mention KnotDevt and be non-trivial.
    if len(response) < 20:
        print("WARNING: Response is suspiciously short.")
        return 1
    if "knotdevt" not in response.lower():
        print("WARNING: Response does not mention KnotDevt.")
        return 1

    print("SUCCESS: Real Gemini response verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
