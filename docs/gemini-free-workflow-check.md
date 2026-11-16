# Gemini Flash-Lite: single-workflow result

The user confirmed key rotation and free-tier eligibility for exactly
gemini-3.5-flash-lite. The earlier document named gemini-3.5-flash; the user's
later explicit model selection took precedence. No billing tier or numerical
quota was independently verified; eligibility was based on that confirmation.

One new job was prepared in the original project:
cffd2566-c315-4120-b8c1-bd98b66ee788. It used three existing synthetic evidence
records visible to the actor and recipient, the persisted Gemini/Flash-Lite
provider snapshot, attempt limit 1, timeout 60 seconds and output limit 1500.
Only that ID was granted free-workflow authorization. Global paid authorization
remained false. Existing queued OpenAI/Gemini jobs were not rewritten or run.

## Actual live outcome

Exactly one generateContent inference request was observed, for Decision Analyst.
It returned HTTP 200. The response failed local structured-output validation and
was not persisted as a successful stage. The error type available in the stage
record is invalid_output; the rejected field/raw response was not retained, so
the exact schema violation cannot be reconstructed from that record.

| Stage | Actual persisted outcome |
| --- | --- |
| Context Collector | succeeded, local |
| Decision Analyst | failed, invalid_output; real Gemini HTTP 200 |
| Work Mapper | failed, stage_failed; guard prevented an inference request |
| Evidence Auditor | not run |
| Readiness Coach | not run |

Job state is failed, attempts 1, error agent_stage_failed. No human-review
checkpoint/draft/publication was created and no fake results were substituted.
All 194 pre-existing job state/attempt/schedule/error rows matched the snapshot.
The one-job grant was removed after failure; original API/worker/Beat were
reloaded with authorization closed. The working 3006/8092 environment was not
restarted. Credential values were never printed or changed.

## Offline correction after the live failure

The previous request only provided JSON mode and a schema in the prompt.
Gemini now receives response_json_schema using its supported subset. Local
validation still uses the complete original JSON Schema and Pydantic model.
Schema bounds unsupported by the provider are retained locally. Required status
fields, known source IDs, exact citation resolution, source policy and human
approval checks remain enforced. Automatic function calling is explicitly off.

Gemini stages now use ChatPromptTemplate -> RunnableLambda(Google GenAI SDK) ->
RunnableLambda(strict validation and citation normalization), composed by
RunnableSequence inside the existing LangGraph nodes. OpenAI LCEL remains intact.

Sanitized diagnostics now log the validator category only, not rejected content,
keys or source text. The single-workflow authorization requires the exact new
job ID, dedicated queue, Flash-Lite model, one attempt and output limit <=1500.
The runtime wrapper serializes model calls, spaces them by 61 seconds, limits
the workflow to three distinct stage calls and stops on any error. It does not
fall back to OpenAI or fake output.

## Verification and remaining blocker

- Full backend suite: 84 passed in 134.86 seconds.
- Additional Gemini adapter tests: all three stages passed offline; combined
  adapter/authorization focused suite: 8 passed.
- Ruff and mypy: passed (81 application source files).
- Frontend TypeScript, ESLint and production build: passed.
- Schema reference: https://aistudio.google.com/docs/structured-output .
- Root API readiness: HTTP 200.
- Corrected response_json_schema path has not been tested with another live call.
- New free-tier run requires renewed authorization after the stopped first run.
- Quotas/RPM/TPM/RPD and actual billing usage remain account-specific and were
  not independently inspected. No further call is made while awaiting approval.

The real Gemini workflow is not yet verified end-to-end.

## Second specifically authorized run and final offline correction

The user explicitly authorized one additional bounded free-tier workflow. New job
245cf753-3f2d-4e2b-9c8b-e85322722c6d used the same model and budgets. It issued
one request, which Gemini rejected with HTTP 400. Decision Analyst persisted
provider_invalid_request; Work Mapper was stopped before a request; the remaining
model stages did not run. No validated live model result or draft was fabricated.
The exact provider rejection detail was not retained by the earlier adapter.

The grant was revoked again. The original API/worker/Beat were restarted with
the gate closed, and the reference environment was preserved. All 214 job rows
existing before this second run retained their metadata. Two live HTTP requests
were made across the two separately authorized attempts: one HTTP 200 with failed
local output validation and one HTTP 400 with no usable model output.

After the 400, schema preflight was tightened further: references are inlined,
provider-unsupported strict-object metadata is omitted from the provider contract,
and the resulting contract is validated by google.genai.types.Schema before any
request. This SDK-native response_schema replaces the unverified
response_json_schema approach described above. Full original JSON Schema and
Pydantic validation still run locally, including extra-field rejection. Offline
tests preflight all three model-stage contracts. Sanitized API diagnostics log
only HTTP status and recognized schema-feature names, never the request/response
body, key or source text.

Final full backend regression: 87 passed in 134.71 seconds. No additional live
request was made to test this final SDK-native schema fix. Another live workflow
requires renewed authorization; neither failed job is reset or overwritten.

## Third bounded run after independent Free Tier verification

Google AI Studio was inspected for the project matching the configured key's
masked identifier: studio-8979632287-46fcf. It showed Free tier, Set up billing,
and Gemini 3.5 Flash Lite limits of 15 RPM, 250K TPM and 500 RPD.
No billing configuration or credentials were changed.

The conditionally authorized new job a21352fe-f315-4f8c-93cd-7cd3ac694c30 used
the existing three evidence records, one attempt and 1500 output tokens maximum.
Only the dedicated worker received a process-local grant for this exact job;
global authorization remained false. The existing API was not restarted.

Exactly one actual inference request was sent (Decision Analyst). It returned
HTTP 400, with the sanitized diagnostic feature `invalid`. No retry or further
provider call was made. Context Collector succeeded; Decision Analyst failed
with provider_invalid_request; Work Mapper failed before inference because the
budget wrapper stopped; Evidence Auditor and Readiness Coach did not run.
The job failed with agent_stage_failed and did not reach human review.

The signed-in actual localhost:3000 frontend displayed these persisted results.
The bounded worker was replaced with a closed-gate worker after the failure;
the process-local grant is no longer active. Existing failed and queued jobs
were preserved. The HTTP 400 remains unresolved; authorization was successfully
established for this run, but a successful real AI workflow is not verified.
