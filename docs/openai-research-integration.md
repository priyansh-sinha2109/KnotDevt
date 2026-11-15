# OpenAI, LCEL and controlled public research

## Findings and resulting configuration

The frontend's Pending badges reflected absent AgentRun rows: no worker or Beat
was executing the queued jobs. Earlier dispatch acceptance only persisted jobs;
the preserved post-commit notification and durable dispatcher now cover delivery
and recovery. An active worker is still necessary.

OpenAI was partially integrated: the adapter already used prompt/model/parser
Runnables, but had a token argument typing issue and selected its provider from
current settings instead of the persisted job snapshot. All three model-powered
LangGraph stages now explicitly pass their saved provider. Context Collector and
Evidence Auditor remain local, as designed. Existing Gemini job snapshots are
not rewritten.

New local processes load LLM_PROVIDER=openai and OPENAI_MODEL=gpt-4o-mini from
the repository .env. Credential values were not changed or printed. Presence is
not proof of validity. The model supports structured output according to
https://developers.openai.com/api/docs/guides/structured-outputs . Account/model
access and key validity remain untested until separate authorization.

LCEL lives in generate_openai in backend/app/agents/provider.py:
ChatPromptTemplate -> ChatOpenAI.with_structured_output -> RunnableLambda.
RunnableSequence explicitly composes these components. The Pydantic parser and
citation normalizer run before output is persisted. The installed constructor's
max_completion_tokens alias enforces the token budget; SDK retries remain off
in favor of the existing bounded stage retries. RunnablePassthrough is unnecessary
because no parallel payload assignment is needed inside these linear pipelines.

## Public research

POST /api/v1/projects/{project_id}/public-research connects the Tavily adapter to
an authenticated project-editor-only preview workflow. Existing session, origin
and CSRF guards apply. PUBLIC_RESEARCH_ENABLED defaults false, and remains false
locally. Enabling it requires explicit operator authorization for live spending.
This gate does not validate credentials or grant project access.

The user supplies a bounded query and one to five public domains. Results retain
retrieval time, provider, URL, public-preview policy and excerpt SHA-256. Every
response states verified=false and requires_authorized_import=true. Nothing is
silently inserted into the evidence graph. Normal authorized source import must
create immutable revisions before an agent can cite the material.

Tavily previews cannot establish authoritative GitHub repository state. Use the
existing GitHub API source comparison for that purpose. Private Notion pages and
meeting notes require authorized uploads/integrations; this route neither logs
into private sources nor advertises a private connector.

## Execution and verification

JOB_QUEUE defaults to celery. API delivery, dispatcher and worker use the same
configured queue. Set a unique JOB_QUEUE alongside a separate database and
deterministic provider for isolated execution. Do not point a new worker or Beat
at the development backlog until historical paid-provider jobs are authorized.

The actual frontend test used a fresh database, a dedicated Redis queue, real
FastAPI and Celery processes, and the built application in Edge. Browser requests
were transparently forwarded to the real isolated API; no workflow responses
were mocked. It submitted a new job, observed five succeeded stage badges,
opened human review and created a draft. PostgreSQL verification confirmed five
successful AgentRun rows and the draft. The isolated processes were stopped and
the test database knotdevt_ui_839a6bd3ae9b was retained. The isolated database used
the local owner role; this was a workflow check, not a substitute for runtime-role
security regression tests.

Offline adapter tests exercise all three LCEL paths with a stub model and test
permission denial, domain filtering and provenance for Tavily. No live model or
search output was represented as a successful live evaluation.

## Remaining live blockers

- Separate confirmation of credential rotation and spending limits.
- Actual OpenAI authentication/model-access and bounded structured-output test.
- Separate authorized Tavily request; public-research operator gate stays off.
- Approved queue/backlog policy before starting the development worker/Beat.
- Historical queued jobs still need their saved providers and explicit execution
  authorization. They have not acquired fabricated successes or substitute output.

Deterministic success is not production readiness.

## Final checks

- Full backend suite: 81 passed in 105.76 seconds.
- Ruff lint, changed-file format checks, and mypy (80 source files): passed.
- Frontend typecheck, ESLint and production build: passed.
- Actual frontend isolated deterministic workflow: five persisted successes and
  a reviewable draft, verified in the fresh database named above.
- Development API readiness: HTTP 200, PostgreSQL and Redis healthy.
- Development worker and Beat: deliberately not started.
- Original job 8c50fe52-801c-458f-abed-d696b0e433f0: queued, zero attempts,
  saved provider Gemini. No live paid requests were issued.
