# Persistent safe local runtime

The normal API on localhost:8080 is left running and unchanged. Its broker uses
Redis database 0 and its historical provider jobs must not be consumed without
authorization. No worker/Beat was running there; the earlier default-queue
inspect commands correctly returned no replies.

The persistent deterministic runtime uses:

- Database: knotdevt_ui_839a6bd3ae9b (previously created synthetic database).
- Redis: 127.0.0.1:56379/14.
- Queue/routing key/exchange: knotdevt-safe-local.
- Node: knotdevt-safe@priyanshsinha.
- Worker: Windows solo pool, concurrency 1.
- Isolated API: http://localhost:8092.
- Actual isolated frontend: http://localhost:3006.

`scripts.safe_local` configures only its own process and children. It refuses a
nonlocal database endpoint, requires the pre-existing isolated database, sets
fake provider and disabled research, blocks live model/research adapters, and
guards execution against non-fake AI requests and unsupported job kinds. It does
not rewrite existing jobs, root .env, or start Beat. This synthetic database uses
the local owner role; it is not a production security configuration.

## Repeatable commands

Do not launch duplicates if these processes are already running. From the
repository root, in a dedicated worker terminal:

```powershell
. .\Enter-KnotDevt.ps1
cd backend
python -m scripts.safe_local worker
```

This wrapper starts the equivalent of Celery `worker --pool=solo --concurrency=1
--queues=knotdevt-safe-local --hostname=knotdevt-safe@%h --loglevel=INFO` after
applying the isolated database/broker settings and runtime guards.

In a separate API terminal (do not restart port 8080):

```powershell
. .\Enter-KnotDevt.ps1
cd backend
python -m scripts.safe_local api
```

In a separate frontend terminal:

```powershell
. .\Enter-KnotDevt.ps1
cd frontend
$env:NEXT_PUBLIC_API_BASE_URL = 'http://localhost:8092/api/v1'
$env:KNOTDEVT_NEXT_DIST_DIR = '.next-safe'
node node_modules/next/dist/bin/next dev --webpack --hostname localhost --port 3006
```

For control verification against the correct broker/database:

```powershell
. .\Enter-KnotDevt.ps1
cd backend
python -m scripts.safe_local inspect
```

Using the default development broker for inspect will not discover the isolated
worker: Redis database 0 and database 14 are separate control channels. The solo
worker may defer control responses while actively executing a task.

## Verified result

Ping returned pong; registered tasks included knotdevt.execute and knotdevt.dispatch;
active_queues listed only knotdevt-safe-local. Direct requests from the actual
frontend at port 3006 reached the API at 8092 (no response mocks or test proxy).
New job 90182802-7479-46ed-9d5a-8a26e26d0a51 completed all five persisted stages
on attempt 1 and reached awaiting_human_review. The browser opened draft
28905f11-9ab6-4fc1-be61-84aa4e3b98b9. A screenshot was saved under the local
KnotDevt temporary directory. All development job state/attempt/schedule/error
rows matched before and after. No paid calls or publication occurred.

Worker, API, and frontend were intentionally left running. Use a separate browser
profile for this synthetic environment because localhost session cookies are
shared across ports. Existing development users are not copied to this database.
