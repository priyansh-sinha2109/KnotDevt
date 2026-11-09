# KnotDevt K0.1.0 backend progress

## Phase 0 · Repository and environment audit

- Recorded repository, runtime, port, and credential findings in [the environment audit](backend-audit.md).
- Audit commit `2f972d5` pushed and verified on `feat/knotdevt-k010-backend`.
- SoloOne confirmed the Round 2 window and the organizer's schedule matched.

## Phase 1 · Backend foundation

- Added FastAPI, versioned health routes, structured request logs, typed errors, PostgreSQL sessions, migration `0001_foundation`, and isolated PostgreSQL 17 and Redis 7 Compose services.
- Two API integration tests passed. Ruff, mypy, Alembic upgrade, and Alembic schema drift checks passed.
- The live API returned 200 with healthy dependencies and 503 while Redis was stopped. The migration revision persisted after PostgreSQL restarted, and readiness recovered.
- Commit `eb881e3` pushed and verified.

## Phase 2 · Authentication and project roles

- Added migration `0002_auth`, Argon2id credentials, signed opaque sessions, Redis login throttling, CSRF checks, audit events, workspace roles, and project assignments.
- The isolated PostgreSQL suite passed six tests, including project administration, cross-workspace denial, privilege escalation, invalid passwords, CSRF, logout and expiration. Ruff, mypy, and Alembic schema drift checks passed.
- Commit `1bc89e5` pushed and verified. Source access rules land with Phase 3 ingestion.

## Phase 3 · Imports and provenance

- Added migration `0003_imports`, bounded JSON adapters, original bytes in private PostgreSQL storage, immutable revisions, owner-managed source policies, and durable Celery dispatch.
- Eight tests passed with PostgreSQL and Redis, including both import formats through a real Celery worker, broker failure recovery, duplicate jobs and revisions, source denial, and grant revocation. Ruff, mypy, and Alembic schema drift checks passed.
- Commit `5f1ef17` pushed and verified.

## Phase 4 · Evidence graph and project scope

- Added migration `0004_evidence`, immutable claim revisions and exact spans, typed relationships, reverse indexes, agent-run storage, PostgreSQL search, a bounded tree, and a text outline.
- Added the non-owner application login and transaction-scoped row security on private imports, source revisions, claims content, and evidence links. Application source grants still apply.
- Nine integration tests passed. Coverage includes exact spans, multi-source withholding, hidden search results, graph pagination, and transaction scope reset. Ruff, mypy, and Alembic checks passed.
- Commit `cbfc82d` pushed and verified.

## Phase 5 · Five-agent execution

- Added migration `0005_agents`, LangGraph fan-out and join, PostgreSQL checkpointing, structured output validation, per-stage budgets and run records, and deterministic and Gemini adapters.
- Eleven tests passed, including five separate stage outputs, review pause, malformed output, visibility loss, and durable worker retries. Ruff, mypy, and Alembic checks passed.
- A bounded Gemini call using synthetic data reached the service and returned HTTP 401. Live output verification requires a working local `GEMINI_API_KEY`.
- Commit `1654457` pushed and verified.

## Phase 6 · Human review and immutable approval

- Added migration `0006_handover`, reviewer corrections, optimistic draft revisions, evidence and audience checks, immutable published versions and rubrics, withdrawal, and durable graph resumption.
- Thirteen tests passed, including concurrent approval, denied roles, immutable published content, later draft corrections, withdrawal, and graph resumption. Ruff, mypy, and Alembic checks passed.
- Commit `3157a90` pushed and verified.

## Phase 7 · Context Trace

- Added version-aware trace schemas and routes with exact source excerpts, timestamps, relationship types, chronological claims, and a text outline.
- Fourteen tests passed, including the proposal, implementation, and conditional approval distinction, unresolved rollback ownership, guessed IDs, and revocation. Ruff, mypy, and Alembic checks passed.
- Commit `03a4d19` pushed and verified.

## Phase 8 · Version-bound readiness

- Added migration `0007_readiness`, fixed-answer grading, version-bound attempts, safety gates, idempotent submission, free-text advisory jobs, and reviewer feedback.
- Sixteen tests passed, including a perfect score blocked by missing prerequisites, guided practice for a resolved package, safe passing status, advisory isolation, and duplicate attempts. Ruff, mypy, and Alembic checks passed.
- Commit `9e061d5` pushed and verified.

## Phase 9 · Receipt, consistency, and security

- Added migration `0008_receipts`, independent idempotent acknowledgements, assignment revocation, stale prerequisite detection, and safe withholding for historical handovers and assessments.
- Nineteen tests passed, including concurrent receipts, historical source revocation, harmless ACL retries, project unassignment, and worker transaction rollback and retry. Ruff, mypy, and Alembic checks passed.
- Commit `5f15578` pushed and verified.

## Phase 10 · Discovery and runtime readiness

- Added paginated workspace, project, review queue, and assigned-version discovery. Source permissions filter draft and version lists before pagination.
- Strengthened readiness to require the current Alembic head and LangGraph checkpoint schema as well as Redis. The live API returned ready.
- Twenty tests passed. Ruff, mypy, and Alembic checks passed.
- Checkpoint `feat(api): add scoped discovery and migration readiness`. Next is the live judge scenario and regression report.
