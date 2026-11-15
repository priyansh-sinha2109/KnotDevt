from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from langchain_core.runnables import RunnableLambda
from pydantic import SecretStr

from app.agents import auditor, fake, provider, research
from app.schemas.agents import CoachInput, ContextBundle, ContextItem


@pytest.mark.parametrize(
    "stage", ["decision_analyst", "work_mapper", "readiness_coach"]
)
def test_lcel_stage_validation_without_network(monkeypatch, stage):
    bundle = ContextBundle(
        task="Verify handover",
        evidence=[
            ContextItem(
                revision_id=uuid4(),
                source_id="S-1",
                event_type="task",
                excerpt="Testing is required. Deployment was approved.",
                event_time="2026-11-14T00:00:00Z",
                related_ids=[],
            )
        ],
    )
    decisions, work = fake.decisions(bundle), fake.work(bundle)
    audit = auditor.audit(bundle, decisions, work)
    output = {
        "decision_analyst": decisions,
        "work_mapper": work,
        "readiness_coach": fake.rehearsal(bundle, audit),
    }[stage]
    data = (
        CoachInput(context=bundle, audit=audit)
        if stage == "readiness_coach"
        else bundle
    )
    captured = {}

    def model(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            with_structured_output=lambda schema, **kw: RunnableLambda(
                lambda prompt: output.model_dump()
            )
        )

    monkeypatch.setattr("langchain_openai.ChatOpenAI", model)
    monkeypatch.setattr(
        provider,
        "settings",
        lambda: SimpleNamespace(
            llm_provider="gemini", openai_api_key=SecretStr("synthetic-only")
        ),
    )
    result = provider.generate(
        stage, data, type(output), "gpt-4o-mini", 10, 900, provider_name="openai"
    )
    assert isinstance(result, type(output))
    assert captured["max_completion_tokens"] == 900
    assert captured["max_retries"] == 0


def test_research_permission_and_provenance_without_network(monkeypatch):
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    client.post.return_value.json.return_value = {
        "results": [
            {"url": "https://github.com/example", "content": "Public snapshot"},
            {"url": "https://private.invalid/page", "content": "Must be excluded"},
        ]
    }
    constructor = Mock(return_value=client)
    monkeypatch.setattr(research.httpx, "Client", constructor)
    monkeypatch.setattr(
        research,
        "settings",
        lambda: SimpleNamespace(tavily_api_key=SecretStr("synthetic-only")),
    )
    with pytest.raises(ValueError):
        research.research("public query", ["github.com"])
    constructor.assert_not_called()
    result = research.research("public query", ["github.com"], permitted=True)
    assert result["verified"] is False
    assert result["requires_authorized_import"] is True
    assert result["access_policy"] == "public_preview"
    assert len(result["results"]) == 1
    assert result["results"][0]["content_sha256"]


@pytest.mark.parametrize(
    "stage", ["decision_analyst", "work_mapper", "readiness_coach"]
)
def test_gemini_lcel_schema_and_validation_offline(stage):
    bundle = ContextBundle(
        task="Synthetic task",
        evidence=[
            ContextItem(
                revision_id=uuid4(),
                source_id="S-1",
                event_type="task",
                excerpt="Testing is required.",
                event_time="2026-11-14T00:00:00Z",
                related_ids=[],
            )
        ],
    )
    decisions, work = fake.decisions(bundle), fake.work(bundle)
    audit = auditor.audit(bundle, decisions, work)
    output = {
        "decision_analyst": decisions,
        "work_mapper": work,
        "readiness_coach": fake.rehearsal(bundle, audit),
    }[stage]
    data = (
        CoachInput(context=bundle, audit=audit)
        if stage == "readiness_coach"
        else bundle
    )
    with (
        patch("app.agents.provider.settings") as config,
        patch("app.agents.provider.genai.Client") as client,
    ):
        config.return_value.gemini_api_key = SecretStr("synthetic-only")
        call = client.return_value.__enter__.return_value.models.generate_content
        call.return_value.text = output.model_dump_json()
        result = provider.generate(
            stage,
            data,
            type(output),
            "gemini-3.5-flash-lite",
            10,
            1500,
            provider_name="gemini",
        )
        assert isinstance(result, type(output))
        sent = call.call_args.kwargs["config"]
        from google.genai import types

        assert sent.response_schema == types.Schema.model_validate(
            provider.gemini_schema(type(output))
        )
        assert sent.automatic_function_calling.disable is True
