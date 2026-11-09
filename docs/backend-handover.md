# KnotDevt K0.1.0 backend handover

Verified on 9 November 2026 IST during the CodersInPune Round 2
implementation window. Team SoloOne used OpenAI Codex for backend
implementation and verification. [Official schedule and AI disclosure rules](https://wecodecoders.in/events/codersinpune)

## Local service status

| Service | Verified state |
| --- | --- |
| FastAPI and Uvicorn | Running on `127.0.0.1:8080`. Liveness, readiness and OpenAPI responded. |
| PostgreSQL | Dedicated Compose PostgreSQL 17.11 on `127.0.0.1:55432`. Eight Alembic migrations are applied at `0008_receipts`. The migration revision persisted after restart. |
| Redis | Dedicated Compose Redis 7.4.12 on `127.0.0.1:56379`. Ready, unavailable and recovered states were exercised. |
| Celery worker and scheduler | Running locally. The active demo completed two imports, agent execution, review resume and advisory processing. |
| Existing environment | Trustchain containers remained healthy. KnotDevt used its own network and volume and left the Windows PostgreSQL instance and stopped containers untouched. |

## Verification and forensic findings

- Regression suite after the Gemini adapter change **23 passed, 0 failed**. Ruff lint and formatting,
  mypy, Alembic head and schema checks passed.
- The first live run exposed missing ORM registration in a standalone Celery
  process. Shared registration fixed it and a fresh-process regression
  now checks foreign key targets. Two subsequent live runs passed, including
  one after demo reset.
- The judge scenario verified PAY-21 as the Friday proposal, C-19 as the
  implementation, and M-07 as conditional Monday approval. Testing and
  rollback ownership remained unresolved, and the missing rationale was
  preserved. A reviewer corrected and approved the exact snapshot and
  rubric. The recipient acknowledged receipt independently of their
  100/100 result, which stayed blocked by the project gap.
- Regression tests exercised source grants, administrator source denial,
  multi-source claims, hidden search results, historical redaction, expired
  sessions, cross-workspace access, duplicate deliveries, failed worker
  writes, concurrent approvals and receipts, and review checkpoint resume.
- k6 2.3.0 issued **1,340 requests in a ten-second run with five virtual
  users** against loopback health endpoints. It observed zero failures,
  **21.98 ms p95** and 12.03 ms mean response time. The sample measures local
  health traffic under this configuration.

## Live Gemini verification

The root `.env` selects `gemini-3.5-flash-lite`. Google lists standard
text input and output on its free tier. The existing project key returned
`READY` from the bounded text request. It also returned a validated
structured decision with one exact citation to a synthetic source.
[Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing)

`gemini-3.6-flash` returned `READY` in its text check. Its structured
check returned HTTP 503 `UNAVAILABLE` after the adapter change. Both
models had rejected the nested schema request with HTTP 400 before the
change. The adapter now uses JSON response mode with the full Pydantic
schema in the system instruction. It validates the response locally
against the original JSON Schema and Pydantic model.

An isolated Celery and PostgreSQL test ran all five stages. Three stages
used Gemini and two ran locally. The Evidence Auditor verified 10 exact
spans across 10 claims. The graph paused before publication, rejected
recipient approval, and resumed after reviewer approval. The approved
Context Trace preserved the proposal, merge and conditional approval.

Gemini initially classified missing testing sign-off and rollback
ownership as generic work items. The first synthetic rehearsal scored
100 and returned `ready_for_scoped_task`. The reviewer reclassified the
two cited claims as a prerequisite and a blocker and approved the
corrected version. The previous version became stale. The corrected
rehearsal scored 100 and returned `blocked_by_project_gap`.

Reviewers must check readiness-gate categories as well as citation
meaning before approving a live-generated draft. Stale versions use
safe withholding or status changes and a manual recheck.

## Repository checkpoints

All feature checkpoints were pushed to
[`feat/knotdevt-k010-backend`](https://github.com/priyansh-sinha2109/KnotDevt/tree/feat/knotdevt-k010-backend).

| Phase | Commit |
| --- | --- |
| Environment audit | `2f972d5` |
| Backend and Compose | `eb881e3` |
| Authentication and permissions | `1bc89e5` |
| Imports and source versions | `5f1ef17` |
| Evidence Tree and project RLS | `cbfc82d` |
| Agent workflow | `1654457` |
| Human approval and immutable versions | `3157a90` |
| Context Trace | `03a4d19` |
| Readiness | `9e061d5` |
| Receipts and security | `5f15578` |
| Discovery and runtime readiness | `bb9796c` |
| Live workflow and regression | `8ff807e` |

- [Local setup](../backend/README.md)
- [Architecture and agents](architecture/k010-backend.md)
- [Database and migrations](database/k010.md)
- [Complete API inventory](api/k010.md)
- [Tests and judge demo](testing/k010.md)
- [Phase-by-phase progress](progress/k010-backend-progress.md)
