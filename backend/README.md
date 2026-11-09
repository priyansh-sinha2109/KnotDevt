# KnotDevt K0.1.0 backend

Requires Docker Desktop with Compose, Python 3.13, and uv. From the repository
root on Windows PowerShell:

```powershell
py -3.13 backend/scripts/init_local.py
docker compose up -d --wait
Set-Location backend
uv sync --locked
uv run alembic upgrade head
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
