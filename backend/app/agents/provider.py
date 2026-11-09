import json

from google import genai
from google.genai import types
from jsonschema import Draft202012Validator
from pydantic import BaseModel

from app.agents.instructions import BOUNDARY, INSTRUCTIONS
from app.core.config import settings
from app.schemas.agents import Stage


def validate_output[Output: BaseModel](raw: str, schema: type[Output]) -> Output:
    payload = json.loads(raw)
    Draft202012Validator(schema.model_json_schema()).validate(payload)
    return schema.model_validate(payload)


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
                system_instruction=f"{BOUNDARY}\n{instruction or INSTRUCTIONS[stage]}",
                response_mime_type="application/json",
                response_json_schema=schema.model_json_schema(),
                max_output_tokens=token_limit,
                temperature=0,
            ),
        )
    if not response.text:
        raise ValueError("Provider returned no structured output")
    return validate_output(response.text, schema)
