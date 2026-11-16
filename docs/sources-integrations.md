# Sources & Integrations: local setup and verification

## UI and evidence

The existing route remains `/app?workspace=<id>&project=<id>&view=sources` on
localhost:3000. The full-width library has server-side search, provider/type
filters, author/time metadata and original links. Manual entry and JSON exports
use an accessible three-step drawer. Selecting a source opens retained revisions
and visible citing claims; selecting a claim opens the existing Evidence Tree.
Light/dark themes, reduced motion and mobile layouts are supported.

Connector data enters existing Source, SourceRevision, ImportPayload and
ImportResult tables. Stable IDs include connection/resource/object identity.
Additive origin columns retain connection and external resource/object IDs.
Unchanged snapshots deduplicate by content fingerprint; observed changes add
revisions. Oversized content explicitly reports truncation at the 12K limit.
Imports are restricted to the connecting owner. Disconnect/revocation hides
retained evidence without deleting history. No connector content is forwarded
to AI services during this task.

Database migrations: 0011_integrations, 0012_source_origins and 0013_integration_events. Existing records
and historical provider snapshots are not rewritten.

## Server configuration

Use placeholders in root `.env.example`. Never use NEXT_PUBLIC for credentials.
Supply an independent Fernet INTEGRATION_ENCRYPTION_KEY generated locally with
Fernet.generate_key(); keep it securely backed up. Tokens are encrypted in
PostgreSQL and omitted from API responses. This task does not overwrite keys.

INTEGRATION_CALLBACK_BASE defaults to
http://localhost:8080/api/v1/integrations. Register exact provider callbacks below.
OAuth state is one-use, session-actor/provider/project bound, and expires after
ten minutes. The frontend return redirect is fixed to localhost:3000; production
deployment requires explicit callback/return URL configuration before release.

### Cloudflare Quick Tunnel edge

Do not point a public tunnel at port 8080. Start the isolated allowlist proxy:

```powershell
cd C:\Users\Hp\Desktop\KnotDevt\backend
.\.venv\Scripts\python.exe -m scripts.oauth_proxy
cloudflared tunnel --url http://127.0.0.1:8090
```

The proxy forwards only `GET /api/v1/integrations/{github|slack|jira}/callback`
and `POST /api/v1/integrations/webhooks/{github|slack}`. Every other path,
including `/docs`, `/openapi.json`, private APIs and admin routes, returns 404.
Raw webhook bodies and signature headers are preserved for the backend's
existing HMAC checks. Set `INTEGRATION_CALLBACK_BASE` to the tunnel HTTPS
origin plus `/api/v1/integrations` before registering OAuth apps; webhook URLs
use that origin plus `/api/v1/integrations/webhooks/github` or `/slack`.

```powershell
$public = "https://<your-quick-tunnel>.trycloudflare.com"
Invoke-WebRequest "$public/docs" -SkipHttpErrorCheck | Select-Object StatusCode
Invoke-WebRequest "$public/api/v1/integrations/github/callback" -SkipHttpErrorCheck | Select-Object StatusCode
```

The first must be 404. The callback may be 422/401/503 without valid OAuth
parameters; that still proves it reached the protected backend.

### GitHub App

Register a GitHub App, enable user authorization and install it on permitted
repositories. Configure GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET. Minimum
read-only permissions for supported content: Metadata, Issues, Pull requests,
Contents and Discussions. Callback: `<base>/github/callback`.

The implementation uses GitHub App user access tokens, whose permissions are
the intersection of user and installed-app access. It does not issue broader
installation JWT credentials. Refresh credentials are stored when returned by
GitHub. Choose the installation and repositories through Manage.

Adapters retrieve repository metadata, issues/PRs, issue comments, PR review
comments, commits and discussion posts with pagination. README selection and
discussion replies remain follow-up work. No bulk code/binary downloads occur.

Set GITHUB_WEBHOOK_SECRET. Delivery URL: `<base>/webhooks/github` on an actual
HTTPS host you control. HMAC SHA-256 and delivery deduplication are required;
events schedule authoritative reconciliation rather than becoming evidence.

### Slack OAuth v2

Create a Slack app; configure SLACK_CLIENT_ID, SLACK_CLIENT_SECRET and
SLACK_SIGNING_SECRET. Callback: `<base>/slack/callback`. Bot scopes:
channels:read, channels:history. User scopes: channels:read, channels:history
for public-channel thread access. The adapter uses the returned user token when
provided. No DM/private channel scopes are requested. Only public member
channels are selectable, and current access is checked before every page.

Subscribe to public channel message and app/access lifecycle events at
`<base>/webhooks/slack`, using your own real HTTPS endpoint. Requests require
Slack signatures and timestamps within five minutes; deliveries deduplicate.
History/replies use pages of 15 with at least 65 seconds between sync pages.
Retry-After is respected. Actual provider/account limits still apply.
Thread replies and observed edits retain snapshots. Deletion handling needs
further live-account verification before release.

### Jira Cloud 3LO

Register an Atlassian OAuth 2.0 3LO app. Add Jira APIs and the callback
`<base>/jira/callback`. Scopes: read:jira-work, read:jira-user, offline_access.
Configure JIRA_CLIENT_ID and JIRA_CLIENT_SECRET. Atlassian returns accessible
sites; project selection is validated against the chosen site. Refresh-token
rotation is encrypted.

Adapters use search/jql, paginated issue comments and changelogs. ADF paragraph
structure and original JSON metadata are retained. Status is never inferred to
mean a blocker. Jira dynamic webhook registration/renewal is not enabled yet;
manual sync and periodic reconciliation are the implemented path. Do not expose
an unsigned Jira webhook as a workaround.

## Separate local services

Dot-source Enter-KnotDevt.ps1 from the repository root, then cd backend.
Use separate terminals:

```powershell
python -m scripts.local_runtime api
python -m scripts.import_worker
python -m scripts.import_worker beat
python -m celery -A app.workers.connector_app.celery worker --pool=solo --concurrency=1 --queues=knotdevt-connectors --hostname=knotdevt-connectors@%h --loglevel=INFO
python -m celery -A app.workers.connector_app.celery beat --loglevel=INFO --schedule "$env:LOCALAPPDATA/KnotDevt/logs/connectors-beat"
```

Do not start a second API if 8080 is already running. New local manual imports
use knotdevt-imports; the import-only worker rejects every non-import job.
Connector workers consume only knotdevt-connectors. Neither queue consumes the
historical AI backlog. No normal AI worker is needed for these services.

Page/resource cursors commit with imported snapshots. Interrupted pages roll
back and replay idempotently. Rate cooldowns and bounded exponential retries
are durable. Connector Beat recovers due syncs without scanning agent jobs.
Complete syncs reconcile again after 30 minutes. Current adapters rescan selected
resources on reconciliation, rather than claiming complete incremental deletion
detection from timestamps alone.

## Additive APIs

- GET projects/{project}/integrations
- POST projects/{project}/integrations/{provider}/connect
- GET integrations/{provider}/callback
- GET/POST integrations/{connection}/resources
- POST integrations/{connection}/sync and /disconnect
- POST integrations/webhooks/github or /slack
- GET sources/{source}/revisions and /claims
- Existing source listing accepts provider and event_type filters.

All paths have the existing /api/v1 prefix. User endpoints preserve project
authorization and mutation CSRF checks; webhook endpoints verify provider HMACs.

## Actual verification and limits

No OAuth app is configured locally, so no live external-account OAuth/sync
success is claimed. Cards show real backend setup-required states. Connector
automated tests use explicitly labeled offline provider fixtures.

The actual localhost:3000 browser verified manual entry and JSON export preview,
successful import through the dedicated worker, source search and retained
revision inspection. Two clearly labeled synthetic verification sources were
added to the demo project and retained. Existing sources were preserved.
Mobile/dark rendering was inspected without document horizontal overflow.
No five-agent execution was triggered; localhost:3006 was not accessed/restarted.

Remaining release gates: register OAuth apps and verify permitted private
repositories, public channels/threads and Jira sites on live accounts; finish
Jira webhook lifecycle, GitHub README/discussion-reply selection and live
revocation/deletion cases before comprehensive connector readiness is claimed.

References:

- https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-user-access-token-for-a-github-app
- https://docs.slack.dev/reference/methods/conversations.history/
- https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-search/
- https://developer.atlassian.com/cloud/jira/platform/webhooks/

### Test results

- Complete backend regression: 120 passed in 155.55 seconds.
- The standalone metadata-registration check retains all assertions with a
  60-second cold Windows subprocess deadline (formerly 15 seconds).
- Webhooks deduplicate transactionally in PostgreSQL, so event effects and the
  deduplication marker commit or roll back together.
- Connector worker ping, registered tasks and exact queue subscription verified:
  knotdevt-connectors, with only connector dispatch/sync tasks registered.
- Import-only worker and its scheduler are running on knotdevt-imports.
- No real provider account synchronization was performed.

- Final focused connector/CSRF suite: 15 passed in 16.63 seconds.
- Ruff passed; mypy passed for 95 application files.
- Alembic check: no new upgrade operations detected.
- Frontend TypeScript, ESLint and production export build passed.
- Browser: manual import job ccb0be54-0080-4fa1-a9c0-cdc4b79274a4
  succeeded with one revision; supported export ui-export-verification-20261115
  also succeeded with one revision. Search found both labeled synthetic records.
- Provider filtering returned an honest empty GitHub result; manual meeting-type
  filtering returned two records. Revision inspection showed the exact content
  fingerprint. Desktop 1440px and mobile 390px layouts had no document overflow.
