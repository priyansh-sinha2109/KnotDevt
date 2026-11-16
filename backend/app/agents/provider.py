import json
import logging
import threading
import time
from typing import Any, cast

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from jsonschema import Draft202012Validator
from jsonschema import ValidationError as JsonSchemaValidationError
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from app.agents.citations import resolve_citation
from app.agents.instructions import BOUNDARY, INSTRUCTIONS
from app.core.config import settings
from app.schemas.agents import (
    Candidate,
    Citation,
    ContextBundle,
    DecisionOutput,
    Stage,
    WorkOutput,
)
from app.schemas.sources import StrictModel


class ProviderOutputError(ValueError):
    """A structured response was absent or could not satisfy its schema."""


class ProviderConfigurationError(RuntimeError):
    """The selected provider cannot run with the deployed configuration."""


class CitationReferenceError(ValueError):
    """A candidate cited a source outside the permitted context."""


class ParallelStageCancelledError(RuntimeError):
    """A parallel peer failed before this stage could make an inference call."""


class InferenceBudgetExceededError(RuntimeError):
    """The locally authorized inference budget was exhausted before a call."""


def reserve_groq_budget(prompt_characters: int, completion_tokens: int) -> None:
    """Atomically reserve conservative daily capacity before external requests."""
    from datetime import UTC, datetime

    from app.core.cache import redis_client

    config = settings()
    if config.groq_self_service_since is None:
        return
    # A character per token deliberately overestimates typical text input.
    tokens = prompt_characters + completion_tokens
    key = "groq-budget:" + datetime.now(UTC).strftime("%Y-%m-%d")
    accepted = redis_client().eval(
        """
        local requests = tonumber(redis.call('HGET', KEYS[1], 'requests') or '0')
        local tokens = tonumber(redis.call('HGET', KEYS[1], 'tokens') or '0')
        if requests + 1 > tonumber(ARGV[1])
            or tokens + tonumber(ARGV[3]) > tonumber(ARGV[2]) then
            return 0
        end
        redis.call('HINCRBY', KEYS[1], 'requests', 1)
        redis.call('HINCRBY', KEYS[1], 'tokens', ARGV[3])
        redis.call('EXPIRE', KEYS[1], 172800)
        return 1
        """,
        1,
        key,
        config.groq_free_daily_request_limit,
        config.groq_free_daily_token_limit,
        tokens,
    )
    if not accepted:
        raise InferenceBudgetExceededError("Groq daily application budget exhausted")


class GroqFinding(StrictModel):
    """Small provider contract; aliases and quotes are resolved locally."""

    kind: str
    status: str
    statement: str
    source_alias: str | None = None
    quote: str | None = None


class GroqExtraction(StrictModel):
    findings: list[GroqFinding]


def gemini_schema(schema: type[BaseModel]) -> dict[str, Any]:
    # The provider accepts a subset; strict business constraints remain enforced
    # against the original schema and Pydantic after extraction.
    allowed = {
        "type",
        "properties",
        "required",
        "enum",
        "items",
        "anyOf",
        "minimum",
        "maximum",
        "minItems",
        "maxItems",
    }
    full = schema.model_json_schema()
    definitions = full.get("$defs", {})

    def clean(value: Any) -> Any:
        if isinstance(value, list):
            return [clean(item) for item in value]
        if not isinstance(value, dict):
            return value
        if "$ref" in value:
            return clean(definitions[value["$ref"].split("/")[-1]])
        result = {}
        for key, item in value.items():
            if key not in allowed:
                continue
            result[key] = (
                {name: clean(child) for name, child in item.items()}
                if key in {"properties", "$defs"}
                else clean(item)
            )
        return result

    return cast(dict[str, Any], clean(full))


def validate_output[Output: BaseModel](raw: str, schema: type[Output]) -> Output:
    try:
        payload = json.loads(raw)
        Draft202012Validator(schema.model_json_schema()).validate(payload)
        return schema.model_validate(payload)
    except (
        json.JSONDecodeError,
        JsonSchemaValidationError,
        PydanticValidationError,
    ) as exc:
        validator = (
            exc.validator
            if isinstance(exc, JsonSchemaValidationError)
            else "json"
            if isinstance(exc, json.JSONDecodeError)
            else "pydantic"
        )
        logging.getLogger(__name__).warning(
            "provider_output_rejected validator=%s", validator
        )
        raise ProviderOutputError("Provider structured output is invalid") from exc


def normalize_citations[Output: BaseModel](data: BaseModel, result: Output) -> Output:
    if not isinstance(data, ContextBundle) or not isinstance(
        result, (DecisionOutput, WorkOutput)
    ):
        return result
    sources = {item.revision_id: item.excerpt for item in data.evidence}
    claims = []
    for claim in result.claims:
        citations = []
        for citation in claim.citations:
            excerpt = sources.get(citation.revision_id)
            if excerpt is None:
                raise CitationReferenceError("Citation references unknown evidence")
            resolved = resolve_citation(excerpt, citation)
            if resolved is None:
                citations.append(
                    citation.model_copy(update={"start": None, "end": None})
                )
            else:
                citations.append(
                    citation.model_copy(
                        update={"start": resolved.start, "end": resolved.end}
                    )
                )
        claims.append(claim.model_copy(update={"citations": citations}))
    return result.model_copy(update={"claims": claims})  # type: ignore[return-value]


def generate[Output: BaseModel](
    stage: Stage,
    data: BaseModel,
    schema: type[Output],
    model: str,
    timeout_seconds: int,
    token_limit: int,
    *,
    instruction: str | None = None,
    provider_name: str | None = None,
) -> Output:
    _reset_request_telemetry()
    selected = provider_name or settings().llm_provider
    if selected == "openrouter":
        return generate_openrouter(
            stage,
            data,
            schema,
            model,
            timeout_seconds,
            token_limit,
            instruction=instruction,
        )
    if selected == "openai":
        return generate_openai(
            stage,
            data,
            schema,
            model,
            timeout_seconds,
            token_limit,
            instruction=instruction,
        )
    if selected == "groq":
        return generate_groq(
            stage,
            data,
            schema,
            model,
            timeout_seconds,
            token_limit,
            instruction=instruction,
        )
    if selected != "gemini":
        raise ValueError("Unsupported live provider")
    credential = settings().gemini_api_key
    if credential is None:
        raise ValueError("Gemini credential is unavailable")
    # Inline references and preflight the reduced contract using the SDK-native
    # Schema model. Full original constraints are still enforced locally.
    contract = json.dumps(schema.model_json_schema(), separators=(",", ":"))
    native_schema = types.Schema.model_validate(gemini_schema(schema))
    from langchain_core.prompt_values import ChatPromptValue
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.runnables import RunnableLambda, RunnableSequence

    def infer(prompt_value: ChatPromptValue) -> str:
        messages = prompt_value.to_messages()
        try:
            with genai.Client(
                api_key=credential.get_secret_value(),
                http_options=types.HttpOptions(
                    timeout=timeout_seconds * 1000,
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            ) as client:
                response = client.models.generate_content(
                    model=model,
                    contents=str(messages[-1].content),
                    config=types.GenerateContentConfig(
                        system_instruction=str(messages[0].content),
                        response_mime_type="application/json",
                        response_schema=native_schema,
                        max_output_tokens=token_limit,
                        temperature=0,
                        automatic_function_calling=types.AutomaticFunctionCallingConfig(
                            disable=True
                        ),
                    ),
                )
        except genai_errors.APIError as error:
            message = (error.message or "").lower().replace("_", "")
            features = [
                word
                for word in (
                    "schema",
                    "responsejsonschema",
                    "responseschema",
                    "additionalproperties",
                    "anyof",
                    "required",
                    "complexity",
                    "depth",
                    "unsupported",
                    "invalid",
                )
                if word in message
            ]
            logging.getLogger(__name__).warning(
                "gemini_request_rejected http=%s schema_features=%s",
                error.code,
                ",".join(features),
            )
            raise
        if not response.text:
            raise ProviderOutputError("Provider returned no structured output")
        return response.text

    prompt = ChatPromptTemplate.from_messages(
        [("system", "{instruction}"), ("human", "{context}")]
    )
    chain: RunnableSequence[dict[str, str], Output] = RunnableSequence(
        prompt,
        RunnableLambda(infer),
        RunnableLambda(
            lambda raw: normalize_citations(data, validate_output(raw, schema))
        ),
    )
    return chain.invoke(
        {
            "instruction": f"{BOUNDARY}\n{instruction or INSTRUCTIONS[stage]}\n"
            "Return JSON. Include every required field. "
            "Prefer at most 3 concise claims. "
            "Use exact quotes from the supplied evidence. "
            f"Return JSON matching this schema:\n{contract}",
            "context": data.model_dump_json(),
        }
    )


def generate_openrouter[Output: BaseModel](
    stage: Stage,
    data: BaseModel,
    schema: type[Output],
    model: str,
    timeout_seconds: int,
    token_limit: int,
    *,
    instruction: str | None = None,
) -> Output:
    """Free-only structured LCEL extraction; no paid model fallback or retries."""
    from langchain_core.prompt_values import ChatPromptValue
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.runnables import RunnableLambda, RunnableSequence
    from openai import OpenAI

    if model != "openrouter/free" and not model.endswith(":free"):
        raise ValueError("OpenRouter requires a free model under the $0 spending limit")
    credential = settings().openrouter_api_key
    if credential is None or not credential.get_secret_value().strip():
        raise ValueError("OpenRouter credential is unavailable")

    def infer(prompt: ChatPromptValue) -> str:
        messages = prompt.to_messages()
        with OpenAI(
            api_key=credential.get_secret_value(),
            base_url="https://openrouter.ai/api/v1",
            timeout=timeout_seconds,
            max_retries=0,
        ) as client:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": str(messages[0].content)},
                    {"role": "user", "content": str(messages[-1].content)},
                ],
                max_tokens=token_limit,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema.__name__,
                        "strict": True,
                        "schema": schema.model_json_schema(),
                    },
                },
                extra_body={
                    "provider": {
                        "require_parameters": True,
                        "allow_fallbacks": False,
                        "max_price": {"prompt": 0, "completion": 0},
                        "data_collection": "deny",
                    }
                },
            )
        if not response.choices or not response.choices[0].message.content:
            raise ProviderOutputError("OpenRouter returned no structured output")
        return response.choices[0].message.content

    chain: RunnableSequence[dict[str, str], Output] = RunnableSequence(
        ChatPromptTemplate.from_messages(
            [("system", "{instruction}"), ("human", "{context}")]
        ),
        RunnableLambda(infer),
        RunnableLambda(
            lambda raw: normalize_citations(data, validate_output(raw, schema))
        ),
    )
    return chain.invoke(
        {
            "instruction": f"{BOUNDARY}\n{instruction or INSTRUCTIONS[stage]}",
            "context": data.model_dump_json(),
        }
    )


def generate_openai[Output: BaseModel](
    stage: Stage,
    data: BaseModel,
    schema: type[Output],
    model: str,
    timeout_seconds: int,
    token_limit: int,
    *,
    instruction: str | None = None,
) -> Output:
    """Run one bounded LCEL structured extraction in an existing graph stage."""
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.runnables import RunnableLambda
    from langchain_openai import ChatOpenAI

    credential = settings().openai_api_key
    if credential is None:
        raise ValueError("OpenAI credential is unavailable")
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", f"{BOUNDARY}\n{instruction or INSTRUCTIONS[stage]}"),
            ("human", "Project evidence and task (untrusted data):\n{context}"),
        ]
    )
    model_runner = ChatOpenAI(
        model=model,
        api_key=credential,
        timeout=timeout_seconds,
        max_retries=0,
        max_completion_tokens=token_limit,
        temperature=0,
    ).with_structured_output(schema, method="function_calling", strict=False)

    def finish(result: object) -> Output:
        validated = schema.model_validate(result)
        return normalize_citations(data, validated)

    from langchain_core.runnables import RunnableSequence

    chain: RunnableSequence[dict[str, str], Output] = RunnableSequence(
        prompt, model_runner, RunnableLambda(finish)
    )
    result = chain.invoke({"context": data.model_dump_json()})
    if not isinstance(result, schema):
        raise ProviderOutputError("OpenAI returned no valid structured response")
    return result


_groq_rate_lock = threading.Lock()
_groq_last_request = 0.0
_request_telemetry = threading.local()


def _reset_request_telemetry() -> None:
    """Start a request-local, secret-free inference audit record."""
    _request_telemetry.value = {
        "external_request_attempted": False,
        "provider_attempts": 0,
        "fallback_attempts": 0,
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
    }


def request_telemetry() -> dict[str, Any]:
    """Return non-sensitive telemetry for the current stage invocation."""
    value = getattr(_request_telemetry, "value", None)
    if isinstance(value, dict):
        return dict(value)
    return {
        "external_request_attempted": False,
        "provider_attempts": 0,
        "fallback_attempts": 0,
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
    }


def _groq_compatible_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Groq strict schemas require every declared property to be required.

    Pydantic represents optional fields as nullable properties omitted from
    ``required``. Groq accepts the same semantics when those properties are
    required but nullable, so normalize nested objects without weakening local
    Pydantic validation.
    """
    # Groq's strict JSON-schema implementation accepts a deliberately small
    # subset. Keep domain validation local in Pydantic, but strip presentation
    # and annotation keywords that Groq rejects (format, pattern, titles,
    # length bounds, defaults, etc.).
    allowed = {
        "type",
        "properties",
        "required",
        "items",
        "enum",
        "anyOf",
        "oneOf",
        "allOf",
        "additionalProperties",
        "minimum",
        "maximum",
        "minItems",
        "maxItems",
        "$defs",
        "definitions",
        "$ref",
    }
    value = {key: item for key, item in schema.items() if key in allowed}
    if isinstance(value.get("properties"), dict):
        value["properties"] = {
            key: _groq_compatible_schema(item) if isinstance(item, dict) else item
            for key, item in value["properties"].items()
        }
        value["required"] = list(value["properties"])
    for key in ("$defs", "definitions"):
        if isinstance(value.get(key), dict):
            value[key] = {
                name: _groq_compatible_schema(item) if isinstance(item, dict) else item
                for name, item in value[key].items()
            }
    for key in ("items", "anyOf", "oneOf", "allOf"):
        item = value.get(key)
        if isinstance(item, dict):
            value[key] = _groq_compatible_schema(item)
        elif isinstance(item, list):
            value[key] = [
                _groq_compatible_schema(entry) if isinstance(entry, dict) else entry
                for entry in item
            ]
    return value


def _groq_wait() -> None:
    global _groq_last_request
    minimum = settings().groq_min_interval_seconds
    with _groq_rate_lock:
        delay = minimum - (time.monotonic() - _groq_last_request)
        if delay > 0:
            time.sleep(delay)
        _groq_last_request = time.monotonic()


def _assemble_groq_findings(
    data: ContextBundle, extracted: GroqExtraction, schema: type[BaseModel]
) -> BaseModel:
    aliases = {f"E{index + 1}": item for index, item in enumerate(data.evidence)}
    claims: list[Candidate] = []
    for index, item in enumerate(extracted.findings[:8]):
        source = aliases.get(item.source_alias or "")
        if source is None:
            raise ProviderOutputError(
                "Groq extraction referenced an unknown evidence alias"
            )
        quote = item.quote or ""
        if not quote:
            raise ProviderOutputError("Groq extraction omitted a supporting quote")
        citation = Citation(revision_id=source.revision_id, quote=quote)
        resolved = resolve_citation(source.excerpt, citation)
        if resolved is not None:
            citation = citation.model_copy(
                update={"start": resolved.start, "end": resolved.end}
            )
        try:
            prefix = "decision" if schema is DecisionOutput else "work"
            claims.append(
                Candidate(
                    key=f"{prefix}_{index + 1}",
                    kind=item.kind,
                    status=item.status,
                    statement=item.statement,
                    citations=[citation],
                )
            )
        except ValueError as exc:
            raise ProviderOutputError(
                "Groq extraction used an unsupported claim value"
            ) from exc
    if schema is DecisionOutput:
        return DecisionOutput(claims=claims, missing_rationale=[], relationships=[])
    return WorkOutput(claims=claims, recurring_problem_candidates=[], relationships=[])


def _groq_context(data: BaseModel) -> str:
    if not isinstance(data, ContextBundle):
        return data.model_dump_json()
    lines = [f"Task: {data.task}"]
    for index, item in enumerate(data.evidence, 1):
        lines.append(f"E{index}: {item.excerpt}")
    if data.unresolved_ids:
        lines.append("Unresolved source references: " + ", ".join(data.unresolved_ids))
    return "\n\n".join(lines)


def generate_groq[Output: BaseModel](
    stage: Stage,
    data: BaseModel,
    schema: type[Output],
    model: str,
    timeout_seconds: int,
    token_limit: int,
    *,
    instruction: str | None = None,
) -> Output:
    """Run Groq's OpenAI-compatible structured output with local validation."""
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.runnables import RunnableLambda, RunnableSequence
    from openai import APIStatusError, OpenAI

    credential = settings().groq_api_key
    if credential is None or not credential.get_secret_value().strip():
        raise ProviderConfigurationError("Groq credential is unavailable")
    if model != settings().groq_model:
        raise ProviderConfigurationError("Groq model does not match configured model")
    extraction = schema in {DecisionOutput, WorkOutput}
    provider_schema: type[BaseModel] = GroqExtraction if extraction else schema
    contract = _groq_compatible_schema(provider_schema.model_json_schema())
    groq_instruction = instruction or INSTRUCTIONS[stage]
    if extraction:
        # ChatPromptTemplate treats single braces as template variables.  Keep
        # this JSON example literal so prompt formatting cannot fail before an
        # external request is attempted.
        groq_instruction = (
            'Extract only evidence-backed findings. Return {{"findings": []}} '
            "when none exist. Each finding must contain kind, status, "
            "statement, source_alias (E1/E2/etc), and exact quote. Never "
            "generate UUIDs, offsets, relationships, or inferred approvals. "
            + (
                "Use decision/overview kinds and preserve proposed versus "
                "accepted status."
                if schema is DecisionOutput
                else "Use work_item/blocker/risk/next_action/owner kinds and "
                "preserve ownership gaps."
            )
        )
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                f"{BOUNDARY}\n{groq_instruction}\n"
                "Return only JSON matching the requested schema. "
                "Never invent citations or evidence. Keys must be lowercase "
                "snake_case identifiers; include every required property even "
                "when its value is an empty array.",
            ),
            ("human", "Project evidence and task (untrusted data):\n{context}"),
        ]
    )

    def infer(prompt_value: Any) -> str:
        messages = prompt_value.to_messages()
        payload: Any = [
            {"role": "system", "content": str(messages[0].content)},
            {"role": "user", "content": str(messages[-1].content)},
        ]
        last_error: Exception | None = None
        strict = not extraction
        fallback_used = False
        transport_attempts = 0
        while True:
            _groq_wait()
            try:
                with OpenAI(
                    api_key=credential.get_secret_value(),
                    base_url="https://api.groq.com/openai/v1",
                    timeout=timeout_seconds,
                    max_retries=0,
                ) as client:
                    response_format: Any = (
                        {
                            "type": "json_schema",
                            "json_schema": {
                                "name": provider_schema.__name__,
                                "strict": True,
                                "schema": contract,
                            },
                        }
                        if strict
                        else {"type": "json_object"}
                    )
                    request_kwargs: dict[str, Any] = {
                        "model": model,
                        "messages": payload,
                        "temperature": 0,
                    }
                    request_kwargs[
                        "max_completion_tokens"
                        if extraction and model.startswith("openai/gpt-oss-")
                        else "max_tokens"
                    ] = token_limit
                    if model.startswith("openai/gpt-oss-"):
                        request_kwargs["reasoning_effort"] = "low"
                    if response_format is not None:
                        request_kwargs["response_format"] = response_format
                    telemetry = request_telemetry()
                    reserve_groq_budget(
                        sum(len(str(item["content"])) for item in payload), token_limit
                    )
                    telemetry["external_request_attempted"] = True
                    telemetry["provider_attempts"] += 1
                    _request_telemetry.value = telemetry
                    response = client.chat.completions.create(**request_kwargs)
                usage = getattr(response, "usage", None)
                if usage is not None:
                    telemetry = request_telemetry()
                    telemetry["prompt_tokens"] = getattr(usage, "prompt_tokens", None)
                    telemetry["completion_tokens"] = getattr(
                        usage, "completion_tokens", None
                    )
                    telemetry["total_tokens"] = getattr(usage, "total_tokens", None)
                    _request_telemetry.value = telemetry
                if not response.choices or not response.choices[0].message.content:
                    raise ProviderOutputError("Groq returned no structured output")
                return response.choices[0].message.content
            except APIStatusError as error:
                last_error = error
                unsupported_schema = (
                    strict
                    and error.status_code in {400, 404}
                    and "response_format" in str(error).lower()
                )
                failed_generation = (
                    strict
                    and error.status_code == 400
                    and "failed_generation" in str(error).lower()
                )
                if unsupported_schema or failed_generation:
                    # Some Groq free-tier responses fail provider-side strict
                    # decoding even when the schema is valid. Retry once in
                    # JSON-object mode; local JSON Schema and Pydantic
                    # validation below remain authoritative.
                    if not fallback_used:
                        strict = False
                        fallback_used = True
                        telemetry = request_telemetry()
                        telemetry["fallback_attempts"] += 1
                        _request_telemetry.value = telemetry
                        continue
                if (
                    error.status_code == 429 or error.status_code >= 500
                ) and transport_attempts < settings().groq_max_retries:
                    transport_attempts += 1
                    time.sleep(0.5 * (2**transport_attempts))
                    continue
                raise
        raise last_error or ProviderOutputError("Groq request failed")

    chain: RunnableSequence[dict[str, str], Output] = RunnableSequence(
        prompt,
        RunnableLambda(infer),
        RunnableLambda(lambda raw: validate_output(raw, provider_schema)),
    )
    result = chain.invoke({"context": _groq_context(data)})
    if extraction:
        return _assemble_groq_findings(data, result, schema)  # type: ignore[return-value]
    return result
