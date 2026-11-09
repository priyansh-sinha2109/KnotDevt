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
- Checkpoint `feat(evidence): add claims and Evidence Tree foundation`. Next is LangGraph.
