# KnotDevt K0.1.0 hosted deployment

This document records the verified reference deployment. It is intentionally
secret-free: credentials, database URLs, session secrets, and provider keys are
managed only in the Vercel and Railway secret stores.

## Topology

```text
Vercel (Next.js)
        |
        v
Railway API ───── PostgreSQL (Neon)
        |
        +──── Redis ─── Celery worker
        |
        +────────────── Celery scheduler
```

## URLs

- Frontend: <https://knotdevt-git-main-priyansh-sinhas-projects.vercel.app>
- API base: <https://knotdevt-api-production.up.railway.app>
- Readiness: <https://knotdevt-api-production.up.railway.app/health/ready>
- Swagger: <https://knotdevt-api-production.up.railway.app/docs>

The frontend receives the API prefix through the Vercel variable
`NEXT_PUBLIC_API_BASE_URL`; the current value is the API URL with `/api/v1`.

## Railway services

The production environment contains four services:

- `knotdevt-api`: `uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- `knotdevt-worker`: `uv run celery -A app.workers.celery_app:celery worker --loglevel=INFO --concurrency=2`
- `knotdevt-scheduler`: `uv run celery -A app.workers.celery_app:celery beat --loglevel=INFO --schedule /tmp/celerybeat-schedule`
- `Redis`: Railway-managed Redis/Valkey service

All application services build from the `backend` directory with the locked
`uv` dependency set. The API health check is `/health/ready`.

## Required secret/configuration names

Set these in Railway only; do not place them in the frontend or repository:

`DATABASE_URL`, `RUNTIME_DATABASE_URL`, `REDIS_URL`,
`SESSION_SIGNING_SECRET`, `GEMINI_API_KEY`, `LLM_PROVIDER`, `LLM_MODEL`,
`AGENT_ATTEMPTS`, `AGENT_TIMEOUT_SECONDS`, `AGENT_TOKEN_LIMIT`,
`SECURE_COOKIES`, `SESSION_COOKIE_SAMESITE`, and `ALLOWED_ORIGINS`.

For separate HTTPS Vercel and Railway origins, use
`SECURE_COOKIES=true`, `SESSION_COOKIE_SAMESITE=none`, and set
`ALLOWED_ORIGINS` to the exact Vercel origin as a JSON array. Never use `*`.

## Database and checkpoints

Run migrations with the owner connection before exposing the API:

```powershell
Set-Location backend
uv run alembic upgrade head
uv run python -m scripts.setup_checkpoints
```

The runtime role needs access to `public` and `agent_checkpoints`, and its
database search path must include both schemas. Do not reset the database or
delete volumes during an update.

## Release and rollback checklist

1. Run backend and frontend checks locally.
2. Push the reviewed commit to `main`.
3. Confirm the Vercel deployment is `READY` and points at that commit.
4. Confirm Railway API, worker, scheduler, and Redis are healthy.
5. Call `/health/ready` and make a browser request from the Vercel origin.
6. For rollback, promote the last known-good Vercel deployment and redeploy the
   matching Railway commit; do not force-push or rewrite history.

No Render service, paid plan, API credit purchase, or billing enablement is part
of this deployment.

## Operational limitations

The reference deployment is a production environment without a separate staging
stack. Use isolated accounts and projects for demonstrations. Gemini usage is
bounded by the configured attempt, timeout, and token limits and remains subject
to the provider account's free-tier quota.
