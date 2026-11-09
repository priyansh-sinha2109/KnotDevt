# KnotDevt K0.1.0 backend

Requires Docker Desktop with Compose, Python 3.13, and uv. From the repository
root on Windows PowerShell:

```powershell
py -3.13 backend/scripts/init_local.py
docker compose up -d --wait
Set-Location backend
uv sync --locked
uv run alembic upgrade head
uv run python -m scripts.setup_runtime_db
uv run python -m scripts.setup_checkpoints
uv run uvicorn app.main:app --host 127.0.0.1 --port 8080 --no-access-log
```

Swagger UI is available at http://127.0.0.1:8080/docs. Liveness is
`GET /health` and `GET /api/v1/health`. `GET /health/ready` verifies the
workspace migration and Redis and returns HTTP 503 if a dependency fails.

From `backend`, create and migrate the separate local test database:

```powershell
uv run python -m scripts.setup_test_db
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv run alembic check
```

The generated root `.env` holds local secrets. The database volume belongs
to this Compose project. Use `docker compose stop` from the root to pause
services while preserving local data.

## Round 2 disclosure

Team SoloOne used OpenAI Codex for backend implementation, test authoring,
and verification during the CodersInPune Round 2 build window from 10:00 IST
on 8 November to 10:00 IST on 11 November 2026.
[Official schedule and rules](https://wecodecoders.in/events/codersinpune)

## Local authentication

Run `uv run python -m scripts.seed_demo` from `backend` to create the reviewer,
recipient, and restricted demo accounts under the `knotdevt.test` domain.
The command prompts for a local password and prints the demo project ID.

Use `POST /api/v1/auth/login` with email and password. Keep the returned
HttpOnly cookie and send the returned `csrf_token` as `X-CSRF-Token` for
authenticated writes. `GET /api/v1/auth/me` recovers the CSRF token, and
`POST /api/v1/auth/logout` revokes the server-side session.

The local loopback HTTP setup uses SameSite=Lax and disables the Secure flag.
Use `SECURE_COOKIES=true` when running the API over HTTPS. Project access
requires both workspace membership and explicit project assignment.

## Import workers

From `backend`, run these in separate terminals:

```powershell
uv run celery -A app.workers.celery_app:celery worker --pool=solo --loglevel=INFO
uv run celery -A app.workers.celery_app:celery beat --loglevel=INFO --schedule .venv/celerybeat-schedule
```

Submit `application/json` to `POST /api/v1/projects/{id}/imports`.
See the typed request examples in `tests/fixtures` and the API schema.
The API accepts a maximum of 1 MiB. A successful submission returns HTTP
202 with a durable job ID. Poll `GET /api/v1/jobs/{id}` for its report.
Use an `Idempotency-Key` to safely repeat the same request bytes.

## Evidence and database scope

The API connects with the non-owner `knotdevt_app` database role.
Alembic uses `DATABASE_URL` and the API uses `RUNTIME_DATABASE_URL`.
Protected PostgreSQL tables require project scope set within the current
transaction. Project membership and source grants are checked separately by
the API before returning any evidence.

Search current source revisions with `GET /api/v1/projects/{id}/sources?query=`
using an exact source ID or PostgreSQL full-text search. Submit claims with
exact source revision IDs and zero-based Unicode span offsets, where the end
offset is exclusive. The evidence tree and text outline include only visible
claims and evidence. The tree returns at most 200 nodes per page including
the root.

## Agent workflow

Queue an agent job at `POST /api/v1/projects/{id}/agent-jobs` with a task,
intended audience IDs, and optional exact source IDs to prioritize. The
collector uses the intersection of the requester’s and audience’s source
permissions. The Decision Analyst and Work Mapper run in parallel. Their
typed outputs feed the Evidence Auditor, which validates exact citations and
flags unsupported material. The Readiness Coach proposes a rehearsal. The
graph checkpoints in PostgreSQL and pauses for human review. The requesting
editor can inspect separate stage outputs with `GET /api/v1/jobs/{id}/runs`.

`LLM_PROVIDER=fake` runs deterministic synthetic fixtures. To enable live
calls, configure `LLM_PROVIDER=gemini`, `LLM_MODEL`, and `GEMINI_API_KEY`
through the shell environment or the ignored root `.env`. Agent calls use
bounded timeouts, token budgets, and recorded retries. Excerpts are
untrusted input. The model adapter has no operational tools.
