import json
import logging
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
from app.schemas.agents import ContextBundle, DecisionOutput, Stage, WorkOutput


class ProviderOutputError(ValueError):
    """A structured response was absent or could not satisfy its schema."""


class CitationReferenceError(ValueError):
    """A candidate cited a source outside the permitted context."""


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
