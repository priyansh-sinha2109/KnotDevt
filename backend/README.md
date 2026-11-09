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

From `backend` with the local database migrated:

```powershell
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
