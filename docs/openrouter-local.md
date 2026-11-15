# OpenRouter local configuration

The adapter uses the existing five-stage LangGraph and LCEL pipelines. It
accepts only `openrouter/free` or model IDs ending in `:free`, sends zero maximum
prompt/completion prices, disables SDK retries and provider fallback, requires
structured-output support and excludes providers that collect data. If no
compatible endpoint exists, the request fails instead of using a paid model.
Full local schema validation, citation normalization and human review remain.

Set these values in the repository root `.env` (never put keys in frontend env):

```dotenv
LLM_PROVIDER=openrouter
OPENROUTER_MODEL=openrouter/free
OPENROUTER_API_KEY=<your key, entered locally>
```

Existing persisted jobs keep their original providers. The global live-provider
authorization stays closed; the Gemini single-job grant does not authorize
OpenRouter. A new bounded OpenRouter execution grant is still needed before
live testing. Do not enable LIVE_AI_AUTHORIZED globally to bypass that gate.

At implementation time OPENROUTER_API_KEY was absent from the root file.
No live OpenRouter request or successful workflow is claimed. Focused offline
adapter/LCEL/authorization tests: 11 passed.

Reference: https://openrouter.ai/docs/guides/routing/routers/free-router

## Subsequent local verification

After the user added the key, a process-scoped OPENROUTER_FREE_JOB_ID grant
was implemented. One new bounded job reached OpenRouter and received HTTP 200,
but Decision Analyst failed local output validation (invalid_output). Context
Collector succeeded; Work Mapper stopped before inference; the remaining stages
did not run. No successful real workflow or human-review draft is claimed.
Historical jobs were not converted to another provider. The earlier key-absence
statement describes the initial integration only.
