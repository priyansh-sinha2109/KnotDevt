"""Unit tests for the chatbot product knowledge module."""

from app.knowledge.product_knowledge import (
    FIVE_AGENTS,
    KNOWLEDGE_TEXT,
    LIMITATIONS,
    OVERVIEW,
    ROLES,
    ROUTES,
    route_for,
)
from app.services.chatbot import _build_system_instruction


def test_knowledge_text_is_substantive() -> None:
    """The assembled knowledge text must contain all major sections."""
    assert "KnotDevt" in KNOWLEDGE_TEXT
    assert OVERVIEW in KNOWLEDGE_TEXT
    assert ROLES in KNOWLEDGE_TEXT
    assert FIVE_AGENTS in KNOWLEDGE_TEXT
    assert LIMITATIONS in KNOWLEDGE_TEXT


def test_five_agents_documented() -> None:
    """All five agents must be named in the knowledge text."""
    for agent in [
        "Context Collector",
        "Decision Analyst",
        "Work Mapper",
        "Evidence Auditor",
        "Readiness Coach",
    ]:
        assert agent in FIVE_AGENTS


def test_limitations_explains_unimplemented_features() -> None:
    """The limitations section must mention voice and Project Help Mode."""
    assert "Voice" in LIMITATIONS or "voice" in LIMITATIONS
    assert "Project Help Mode" in LIMITATIONS


def test_routes_only_contain_valid_paths() -> None:
    """Every route must start with / (no fabricated external URLs)."""
    for key, info in ROUTES.items():
        assert info["path"].startswith("/"), f"Route {key} has invalid path"
        assert "label" in info
        assert "auth" in info


def test_route_for_returns_known_views() -> None:
    assert route_for("projects") is not None
    assert route_for("sources") is not None
    assert route_for("ai_workflow") is not None
    assert route_for("evidence") is not None
    assert route_for("review") is not None
    assert route_for("versions") is not None
    assert route_for("readiness") is not None
    assert route_for("nonexistent") is None


def test_system_instruction_guest_context() -> None:
    """Guest system instruction must include the boundary and guest context."""
    instruction = _build_system_instruction(None, "landing")
    assert "KnotDevt Guide" in instruction
    assert "PRODUCT KNOWLEDGE" in instruction
    assert "Guest" in instruction
    assert "landing page" in instruction


def test_system_instruction_auth_context() -> None:
    """Authenticated instruction must include the authenticated context."""
    instruction = _build_system_instruction(None, "projects")
    assert "KnotDevt Guide" in instruction
    assert "Projects" in instruction or "projects" in instruction.lower()
