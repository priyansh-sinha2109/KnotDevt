# KnotDevt AI Guide Chatbot

A floating AI assistant that helps users understand and navigate the KnotDevt
platform. It uses the existing Gemini provider for real inference — no fake
answers, no hardcoded responses, no silent fallback to other providers.

## Architecture

```
Frontend (Next.js)                      Backend (FastAPI)
┌──────────────────────┐               ┌─────────────────────────────┐
│ ChatbotWidget         │               │ /api/v1/chatbot/*           │
│  (floating, lazy)     │ ──HTTP──>     │  availability               │
│  Framer Motion        │               │  messages (POST)            │
│  Markdown rendering   │               │  sessions (GET/DELETE)      │
│  Theme-aware          │               │                             │
└──────────────────────┘               │ services/chatbot.py          │
                                       │  ├─ knowledge/ (grounding)   │
                                       │  ├─ chatbot_provider.py      │
                                       │  │    (Gemini free-text call) │
                                       │  └─ db/chatbot.py (sessions)  │
                                       └─────────────────────────────┘
```

The chatbot is **separate** from the five-agent LangGraph workflow. It does not
invoke `app.agents.graph.run_graph`, `app.agents.provider.generate`, or any
agent stage. It makes a single bounded `generate_content` call per message.

## Modes

### Guide Mode (implemented)

Available throughout the website — landing page, login, and all workspace views.

- **Guest users**: Can ask about KnotDevt features and public documentation.
  Cannot access any workspace, project, or source data.
- **Authenticated users**: Receive page-specific guidance. Still cannot access
  specific project data, source content, or other users' information.

### Project Help Mode (architectural boundary, K0.2.0)

Not implemented. The knowledge base's `LIMITATIONS` section explicitly states
this mode is reserved for K0.2.0. The guide chatbot does not falsely present
it as available. The architectural boundary is maintained by:

- The `OptionalActor` dependency distinguishes guest vs authenticated access.
- The system instruction prohibits answering project-specific questions.
- The service layer does not query project, source, or evidence tables.
- The `ChatAvailability.mode` field returns `"guide"` or `"guide_guest"`,
  never `"project_help"`.

## Backend configuration

The chatbot uses the existing Gemini credential and model from `.env`:

| Variable | Purpose |
| --- | --- |
| `GEMINI_API_KEY` | Private Gemini credential (required for live calls) |
| `LLM_MODEL` | Gemini model name (e.g. `gemini-3.5-flash-lite`) |
| `AGENT_TIMEOUT_SECONDS` | Request timeout (default 25s, capped at 60s) |
| `AGENT_TOKEN_LIMIT` | Max output tokens (capped at 1200 for chat) |

The chatbot does **not** use `LLM_PROVIDER`. It always uses Gemini directly.
If `GEMINI_API_KEY` is absent or empty, the `/chatbot/availability` endpoint
returns `available: false` and message sending returns a 503 error with code
`guide_not_configured`.

### Error handling

| HTTP | Error code | Meaning |
| --- | --- | --- |
| 429 | `guide_quota_exhausted` | Free-tier quota exhausted — do not retry |
| 503 | `guide_auth_unavailable` | API key invalid (401/403) |
| 503 | `guide_model_unavailable` | Model not found (404) |
| 503 | `guide_not_configured` | No API key configured |
| 503 | `guide_temporarily_unavailable` | Timeout or 5xx — retry may help |
| 503 | `guide_request_invalid` | Request rejected (400) |
| 503 | `guide_unavailable` | Unknown provider error |

Failed messages are stored in the database with their error code. The frontend
shows a truthful error state and a retry button — never a simulated success.

### Rate limiting

- 20 messages per 60 seconds per client (Redis-based).
- Rate limiting fails open if Redis is unavailable.

### Database

Chatbot tables are separate from agent workflow tables:

- `chat_sessions` — Session metadata (user_id nullable for guests, page_context)
- `chat_messages` — Messages (role, content, error_code)

Migration: `0010_chatbot_guide` (down_revision `0009_job_queue`).

Session ownership is enforced server-side:
- Authenticated users can only access their own sessions.
- Guests cannot list or retrieve sessions.
- Cross-user access returns 404 (not found).

## Frontend configuration

The widget is lazy-loaded via `next/dynamic` with `ssr: false` so it does not
slow down the initial page load or the static export.

### Theme adaptation

The widget detects dark mode by observing the `.workspace.dark` class via a
`MutationObserver`. It applies a `chatbot-dark` class to its root element,
which switches CSS variables. The landing and login pages use the light palette.

### Markdown safety

The `ChatMarkdown` component renders markdown through JSX — never
`dangerouslySetInnerHTML`. Only a subset of markdown is supported (headers,
bold, italic, code, lists). Links are only rendered for internal paths
starting with `/`; external URLs appear as plain text.

### Accessibility

- `role="dialog"` and `aria-label` on the panel
- `role="log"` with `aria-live="polite"` on the messages area
- Keyboard: Enter to send, Escape to close
- `prefers-reduced-motion` disables animations

## API endpoints

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/api/v1/chatbot/availability` | Optional | Check if AI guide is configured |
| POST | `/api/v1/chatbot/messages` | Optional | Send a message (CSRF for authed) |
| GET | `/api/v1/chatbot/sessions` | Authenticated | List sessions |
| GET | `/api/v1/chatbot/sessions/{id}` | Authenticated | Get session detail |
| DELETE | `/api/v1/chatbot/sessions/{id}` | Authenticated | Delete session |

## Testing

### Backend

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/unit/test_chatbot_knowledge.py tests/integration/test_chatbot.py -v
```

Tests mock `generate_chat` so no live API calls are made. They verify:
- Guest and authenticated access isolation
- CSRF enforcement for authenticated POST/DELETE
- Cross-user session access blocked (404)
- Quota exhaustion returns 429 (not a simulated success)
- Empty and oversized messages rejected (422)
- OpenAPI schema documents chatbot endpoints

### Frontend

```powershell
cd frontend
npx tsc --noEmit
npx eslint src/chatbot/ app/layout.tsx
npx next build --webpack
```

## Live Gemini test

Before any live call, verify free-tier eligibility and request explicit
approval. See the "Bounded Live Test" section in the implementation report.

The chatbot uses `gemini-3.5-flash-lite` (the model configured in `.env` and
the verified free-tier model in `provider_authorization.py`). A single bounded
call with synthetic input is sufficient to verify real integration.
