# Reliability fix and verification report

Date: 2026-11-13. Work performed in the existing `main` working tree.

This pass implements targeted reliability changes, not a rewrite of the 30
workflow families. Existing OpenAI/LCEL, Tavily, citation, configuration and
database connection changes were preserved. No live provider calls, production
data changes, database resets, volume deletion, commits, pushes or deployments
were performed. Docker Desktop and the existing local PostgreSQL/Redis containers
were started. Tests use the guarded `knotdevt_test` database and Redis database 15.

## Findings, fixes and scenarios

| Issue / classification | Root cause and reproduction | Files changed | Fix | Regression evidence / result | Remaining risk |
| --- | --- | --- | --- | --- | --- |
| Polling stops on transient error — confirmed bug | Return 503, abort a network request, or hold response past deadline while observing a job | `frontend/src/project-work.tsx`, `frontend/tests/polling-recovery.mjs` | Five automatic retries, exponential delay with jitter, 15-second request deadline, cancellation, preserved result/job ID, manual status retry | Real Edge browser against built app with intercepted API faults: 503 recovery, network recovery, timeout recovery, terminal stop, 403 stop, manual recovery, navigation cancellation all PASS | Continuous valid queued responses keep polling, intentionally. Retry-After header is not yet consumed. |
| Checkpoint reconciliation stops after infrastructure failures — reproduced reliability risk | Publish; inject four connection failures; then commit checkpoint and fail before job commit | `backend/app/workers/celery_app.py`, `services/review_resume.py`, new recovery tests | Committed approval remains durable intent; infrastructure failures retain queued resume with sanitized error and exponential delay capped at one hour. Dispatcher recovers legacy exhausted `processing_failed` resumes linked to approvals. Resume requires matching version, project and approving actor | PostgreSQL/checkpoint-backed scenario PASS: queued after four failures, resumed after partial success, duplicate delivery no-op, exactly one unchanged version | Requires worker and scheduler availability. Missing/corrupt checkpoint or missing approval is terminal and needs operator investigation; no automatic fabrication of history. |
| Published job still reports human review — confirmed misleading projection | Inspect original agents job after publishing and before/after resume | `services/jobs.py`, `schemas/sources.py`, generated `frontend/src/api-schema.ts`, `project-work.tsx` | Derive `reconciling`, `reconciliation_failed`, or `succeeded` from latest version's resume job; UI describes publication separately from checkpoint completion | Included in code/type verification; checkpoint integration exercises the underlying states | New phase enum values require API consumers to accept updated contract. |
| Duplicate publication — already guarded | Concurrent approval of same draft revision | Existing `test_handover.py`; no approval algorithm change | Preserve project lock, expected revision and content-hash uniqueness | Existing concurrent publication test PASS: one 201, one 409, one version | Retried HTTP approval returns conflict, not an idempotent 201 response; client can open existing version. |
| OpenAI errors collapsed into generic retry — confirmed classification gap | Construct SDK authentication, rate-limit, outage and timeout exceptions | `agents/graph.py`, `tests/unit/test_agent_errors.py` | Sanitized OpenAI HTTP/connection/timeout classifications; auth/quota do not retry; temporary failures use bounded stage/job recovery | Offline SDK exception regression PASS; no paid API calls | Invalid JSON/schema/missing-field/enum errors share `invalid_output`; unexpected application errors retain existing generic bounded handling. |
| Work Mapper missing required status — recovery scenario | Inject first response without claim status, then return valid structured output | New `test_reliability_recovery.py` | Preserve strict validation and existing bounded repair/retry mechanism | PASS: failed invalid-output attempt then successful attempt; successful Decision Analyst executed once | This exercises deterministic injected output through the real graph and database, not a live provider. |
| Ambiguous / unknown citations — already improved in initial working tree | Repeated quote without unique occurrence; citation outside context | Preserved existing `provider.py` and citation tests | Ambiguous citation retains no fabricated offsets and reaches auditor; unknown revision is rejected; unsupported interpretation remains subject to audit/human review | Citation, generalization and contract tests PASS | Exact quote matching is not semantic verification. |
| Invitation consumed before commit — reproduced reliability risk | Fail database commit during redemption; retry concurrently from two clients | `api/invitations.py`, new recovery tests | Serialize by project lock, recheck Redis record/permissions, commit membership and hashed redemption marker together, delete Redis record after commit | PASS: failed transaction creates no membership; concurrent retry yields one success and one 404; intended account obtains membership | Redis cleanup failure leaves an unusable token until TTL; durable marker blocks replay. Hash marker lookup currently has no dedicated index. |
| Failed import cannot be retried under same key — confirmed recovery gap | Inject three import connection failures; replay original idempotency key; explicitly retry twice | `api/sources.py`, `services/jobs.py`, `project-work.tsx`, generated API schema, recovery tests | Explicit authenticated owner/editor retry endpoint; only `processing_failed` jobs may restart; same job/key/content retained; permanent input/access failures rejected | PASS: replay returns same failed job; explicit retry and duplicate delivery produce two expected sources without duplicates | Attempt counter restarts for an explicit retry; no separate attempt-history table introduced. |
| Job executing/queued ambiguity — intentional current storage limitation | Worker holds transaction while work executes | No persisted execution-state migration | Preserve existing queue/transaction-lock/crash-redelivery behavior; do not invent running percentages/provider activity | Existing real Celery integration and rollback/duplicate-delivery tests PASS | Public job state still lacks a reliable executing lease for all job kinds. Deferred rather than introduce unverified lifecycle migration. |
| High-impact claim correction with contradictory-only citation — confirmed guard gap | Patch confirmed/implemented/resolved using only a contradicting exact quote | `services/drafts.py`, recovery tests | Require supporting evidence and reject contradictory evidence for high-impact states; preserve human justification and immutable revisions | Dedicated allowed/forbidden transition regression added; final suite result below | Reviewer remains responsible for semantic support; no arbitrary status-transition matrix introduced. |
| Review confirmation survives changed decisions — confirmed UI gap | Confirm, then edit a claim decision or add/change/remove a gap | `frontend/src/review.tsx` | All decision/gap mutations clear confirmation; claim correction already remounts revision-bound editor | Typecheck/lint/build PASS; handler review completed | Dedicated browser interaction scenario for this change remains unexecuted. |
| Registration succeeded but sign-in failed — confirmed recovery gap | Registration succeeds, subsequent login errors | `frontend/app/login/page.tsx` | Switch to sign-in mode after successful registration; explicitly explain account exists if login fails | Typecheck/lint/build PASS | Dedicated registration fault-injection browser test remains unexecuted. |
| Alembic proposes dropping checkpoint tables — reproduced verification risk | Run Alembic check with app search path exposing LangGraph tables | `backend/alembic/env.py` | Exclude the four LangGraph-owned tables from app autogeneration; retain checks for other drift | PASS: no new upgrade operations detected | No migration or table modification performed. |
| Two brittle synthetic workflow assertions — pre-existing test drift | Generic fixture now emits extra prerequisite and multiple accepted decisions | `tests/integration/test_critical_gaps.py`, `scripts/verify_local.py` | Assert required testing/rollback findings while permitting extra findings; select intended linked Monday claim by statement instead of arbitrary status-map winner | Both failing tests now PASS; safety assertions remain | Deterministic demo script intentionally identifies its known synthetic claim. |

## Verification

- Initial unit baseline: 32 passed.
- Intermediate full suite: 65 passed (116.72 seconds).
- Additional Work Mapper recovery test: passed with the other three recovery tests.
- Final full suite: **67 passed in 106.85 seconds**.
- Ruff lint and format: passed.
- mypy: passed, 79 source files.
- TypeScript: passed, including regenerated API contract.
- ESLint: passed.
- Production static build: passed.
- Edge browser fault scenarios: all seven passed against the production build.
- Alembic check on isolated test database: passed; no new migrations required.
- `git diff --check`: passed; Git reports existing LF/CRLF conversion warnings.

The backend tests use real local PostgreSQL, Redis and checkpoint storage, with
deterministic fault injection at failure boundaries. The existing full workflow
test runs a real Celery worker. A hard OS process kill and an actual container
network outage were **not** executed; injected exceptions/rollback are not
reported as those stronger tests. No existing database or Redis contents were
flushed to prepare the suite.

## Scope decisions and remaining release blockers

1. Live OpenAI/Tavily evaluation is blocked by the required separate credential
   rotation confirmation and spending authorization. No request was made.
2. Hard worker termination, actual PostgreSQL/Redis interruption, exhausted
   browser retry timing, invitation expiry during a lock wait, Redis cleanup
   failure, and dedicated browser review-confirmation/login recovery scenarios
   need additional verification before claiming the entire requested fault
   matrix is complete. Existing tests cover permission isolation, stale
   assessment gates, duplicate delivery, and immutable published content.
3. Permanently missing/corrupt checkpoint history is reported as reconciliation
   failure and requires operator repair; it does not withdraw a valid version.
4. Persisted executing leases, shared-resource automatic retry, distinct import
   file-reading state, safe in-memory recovery across session expiry, and an
   additional stale-assessment warning were not implemented in this focused
   pass. Existing backend access/readiness gates remain authoritative.
5. Source history/deletion remains intentional: historical content is not
   promoted and deleted sources are not silently restored. Explicit restore
   workflows are deferred under phase 10's scope allowance.
6. New phase enum values are an additive API change but can break exhaustive
   consumers. Generated frontend types are updated. The new POST job-retry
   endpoint is additive. Persisted job states and database schema are unchanged.

This report does not declare production readiness or completion of every phase
in the supplied action plan. Remaining scenarios above are explicit verification
gaps; passing unit tests alone is insufficient release approval.

## Working tree

All changes remain uncommitted on main. Pre-existing changes preserved:
`.env.example`, `agents/graph.py`, `agents/provider.py`, `core/config.py`,
`db/session.py`, `services/agents.py`, `pyproject.toml`, the agent-contract and
citation tests, `uv.lock`, untracked `agents/research.py`, and the prior audit.

This pass additionally changes migration filtering, invitation/import APIs,
job/schema projections, draft guards, resume/worker recovery, demo verification,
critical-gap/error tests, login, generated API types, polling and review UI. New
files: `backend/tests/integration/test_reliability_recovery.py`,
`frontend/tests/polling-recovery.mjs`, and this report. The full tracked diff at
report preparation is 25 files, 512 insertions and 48 deletions, **including
pre-existing changes**; new untracked test/report files are not in that stat.
