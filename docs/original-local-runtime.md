# Original application: new-job routing and authorization

The original app remains localhost:3000 -> localhost:8080 -> knotdevt database
on PostgreSQL port 55432 -> Redis port 56379, database 0. New jobs use queue
knotdevt-local-new. OpenAI/gpt-4o-mini remains selected. LIVE_AI_AUTHORIZED is
false; no credential validity, rotation or spending authorization is assumed.

The working synthetic app uses ports 3006/8092, a separate synthetic database,
Redis database 14 and queue knotdevt-safe-local with deterministic output.
Those processes were not restarted or repointed.

## Root cause and fix

The original runtime had no worker or Beat. The isolated worker could not see its
database or Redis control/queue channel. Historically, absent AgentRun rows were
rendered as Pending without distinguishing provider authorization.

Migration 0009 adds a nullable queue column with no server default/backfill.
Historical rows keep NULL and are not assigned to any new consumer. Newly
inserted jobs receive the configured queue. Post-commit notification publishes
to that persisted queue; worker execution and dispatcher recovery require a
matching queue. Historical jobs are not migrated, deleted or executed.

The live-provider gate is checked before attempts increment or LangGraph runs.
The API projects queued live-provider jobs as awaiting_provider_authorization;
the original frontend displays Awaiting AI provider authorization rather than
Pending. Polling pauses in this state. Beat does not repeatedly dispatch blocked
AI jobs. Celery can acknowledge receipt of a blocked delivery without marking
the PostgreSQL job succeeded or creating any stage outputs.

## Repeatable startup

The following processes are already running; do not start duplicates. Open a
PowerShell terminal at C:\Users\Hp\Desktop\KnotDevt for each command group.

Original API, only when it is not already running:

```powershell
. .\Enter-KnotDevt.ps1
cd backend
python -m scripts.local_runtime api
```

Original new-job worker:

```powershell
. .\Enter-KnotDevt.ps1
cd backend
python -m scripts.local_runtime worker
```

Recovery scheduler:

```powershell
. .\Enter-KnotDevt.ps1
cd backend
python -m scripts.local_runtime beat
```

Inspect the original runtime:

```powershell
. .\Enter-KnotDevt.ps1
cd backend
python -m scripts.local_runtime inspect
```

Original frontend, only when it is not already running:

```powershell
. .\Enter-KnotDevt.ps1
cd frontend
$env:NEXT_PUBLIC_API_BASE_URL = 'http://localhost:8080/api/v1'
Remove-Item Env:KNOTDEVT_NEXT_DIST_DIR -ErrorAction SilentlyContinue
npm run dev
```

The wrapper uses Windows solo pool/concurrency 1 and consumes only
knotdevt-local-new. It refuses another database, fake provider, wrong queue or an
open paid-provider gate. Its model/research adapters also fail closed. Do not use
the generic default-queue worker to consume the old backlog. A future live rollout
requires explicit rotation/spending approval and a separate review of the guards.

## Demonstrated behavior

The browser on localhost:3000 directly used only localhost:8080 API requests,
submitted OpenAI job d0d0c6ae-042f-483b-a0f6-b8eeeb99e316, and displayed the new
authorization message and five authorization-wait badges. Saved provider/model
were openai/gpt-4o-mini; persisted queue was knotdevt-local-new; attempts remained
zero and AgentRun rows remained empty. Worker logs confirmed receipt and the
authorization guard. Two synthetic evidence imports succeeded through the same
original API and worker. No API responses were mocked and no fake provider was
substituted for OpenAI.

All 177 historical job metadata/provider/model rows matched the pre-change
snapshot and remained unassigned. No paid requests were issued. Original 8080
was reloaded once to load the necessary schema/API changes; 8092 was untouched.

Backend regression: 83 passed; mypy and Ruff passed. Queue migration passed on
the original and test databases without resetting either. The original AI job
is not a completed workflow: it correctly awaits spending/rotation authorization.
