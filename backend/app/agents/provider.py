import json

from google import genai
from google.genai import types
from jsonschema import Draft202012Validator
from pydantic import BaseModel

from app.agents.citations import resolve_citation
from app.agents.instructions import BOUNDARY, INSTRUCTIONS
from app.core.config import settings
from app.schemas.agents import ContextBundle, DecisionOutput, Stage, WorkOutput


def validate_output[Output: BaseModel](raw: str, schema: type[Output]) -> Output:
    payload = json.loads(raw)
    Draft202012Validator(schema.model_json_schema()).validate(payload)
    return schema.model_validate(payload)


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
                raise ValueError("Citation references unknown evidence")
            resolved = resolve_citation(excerpt, citation)
            if resolved is None:
                raise ValueError("Citation occurrence is not uniquely identified")
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
) -> Output:
    credential = settings().gemini_api_key
    if credential is None:
        raise ValueError("Gemini credential is unavailable")
    # This Gemini model rejects nested response_schema contracts containing
    # Pydantic's strict-object keywords. Keep the contract in the instruction
    # and strictly validate the returned document locally.
    contract = json.dumps(schema.model_json_schema(), separators=(",", ":"))
    with genai.Client(
        api_key=credential.get_secret_value(),
        http_options=types.HttpOptions(
            timeout=timeout_seconds * 1000,
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    ) as client:
        response = client.models.generate_content(
            model=model,
            contents=data.model_dump_json(),
            config=types.GenerateContentConfig(
                system_instruction=(
                    f"{BOUNDARY}\n{instruction or INSTRUCTIONS[stage]}\n"
                    "Every required field, including every claim status, must be "
                    f"present. Return JSON matching this schema:\n{contract}"
                ),
                response_mime_type="application/json",
                max_output_tokens=token_limit,
                temperature=0,
            ),
        )
    if not response.text:
        raise ValueError("Provider returned no structured output")
    return normalize_citations(data, validate_output(response.text, schema))
