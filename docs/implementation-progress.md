# KnotDevt implementation and verification

Branch `feat/knotdevt-k010-backend`. Changes remain in the working tree.

## Implemented

- Personal registration, session login, workspace and project setup, and email-based recipient selection. A workspace administrator can assign an existing member or share a one-time, one-hour invitation. The signed-in account must match the invited email. Invite redemption grants only recipient access to the selected project and its workspace. Existing roles are preserved.
- Guided issue/task, meeting and conversation entry. Supported JSON exports can be selected and previewed before submission. The source library supports search and exact source browsing. Imports retain server validation, permissions and real worker status.
- Dark sidebar, light/dark workspace theme, project actions and activity cards backed by permitted drafts and published handovers.
- React Flow and ELK evidence diagram, selected-edge particles, branch controls, zoom and fit, and a text outline. Approved diagrams use the authorized version trace. Review uses source names, dates and exact supporting excerpts with immutable revision IDs in requests.
- Shared homepage/login SVG transition, first-load intro, smoothed desktop pointer and reduced-motion logo treatment. Existing Lenis and GSAP storytelling remain in place.
- Public API configuration and documented cookie-compatible hosting topology. No GitHub connector or deployment.

## Local verification

- Local services use frontend `http://localhost:3000` and FastAPI `http://localhost:8080`. PostgreSQL and Redis were restarted using their existing containers after Docker Desktop was unavailable. Worker and Beat process existing queues.
- Playwright-controlled Microsoft Edge passed registration, login, workspace creation, project creation and layout checks at 1440×900, 1280×800, 768×1024 and 390×844. All three guided entry modes persisted through Celery. A separate newly registered account redeemed its invitation and appeared in the recipient selector.
- Full Edge runs passed with both the seeded project and a newly registered workspace. The personal flow created both accounts, issued and redeemed the invitation, previewed and imported both supported file types, verified restricted evidence stayed hidden, ran all five agents, corrected a claim using an exact citation, reviewed gaps, published, opened Context Trace, completed the assessment, acknowledged receipt and logged out. The persisted agent runs included the configured `gemini-3.5-flash-lite` model. The recipient scored 100/100 and remained blocked by the project gap. The tests' unexpected-console-error assertions passed.
- Edge confirmed real desktop pin/scrub, cursor tracking, marquee, parallax, changing logo stroke, first-load intro, the blue public transition in both directions, tablet layout and reduced-motion mobile fallback.
- The final backend regression suite passed 30 tests. Ruff, Ruff format, mypy and Alembic checks passed. TypeScript, ESLint and the Next.js production build passed.
- Evidence captures are in the Windows temp directory, including `knotdevt-edge-setup-{1440,1280,768,390}.png`, `knotdevt-edge-guided-import.png`, `first-load-intro.png`, `blue-login-transition.png`, `workspace.png`, `evidence-diagram.png` and `readiness-mobile.png`.

## Remaining scope and continuation

- The invitation code is shared privately by the administrator. Email delivery and mailbox verification are outside this implementation. Hosted cookie behavior needs validation against the actual HTTPS topology when deployment is separately authorized.
- Preserve the uncommitted working tree and seeded data. The isolated backend tests used `knotdevt_test` with process-only port overrides to 55465. See `git status --short` for the complete list of working-tree changes, including earlier login and hosting work.

## WALA claim and evidence repair

- Read-only inspection found 11 claims in the existing College Event Registration draft. The stored source is a manually entered task summary. The model quotes for the overview and next-action claims had zero verbatim hits in their correct revision. Other exact quotes described repository status and did not establish human decisions, monitoring, ownership or contacts. The original draft and source remain intact.
- The updated prompts distinguish status from human decisions and ask for whole-claim support. A narrow deterministic path for the recognized single Renovate summary extracts one overview, two open work items and one unresolved blocker, all from exact stored sentences. It falls back to regular auditing for other evidence or unrecognized text. The result makes no confirmed human ownership or contact claim.
- Audit distinguishes exact spans from semantic review. Corrections revalidate exact offsets against visible immutable source revisions. Missing support, remaining contradictions and semantic review are explicit after editing. Existing revision and approval safety checks remain in force.
- Source library comparison uses the authenticated, CSRF-protected `/sources/{source_id}/public-issue` endpoint. It requests the single allowed official public GitHub API URL, caps the response and returns exact body text, timestamps and a snapshot fingerprint. Comparison is read-only and does not replace the stored summary or create verified citations.
- Review rows and the compact tree open the large Evidence Explorer over the current review. It separates claim navigation, labeled graph and exact details. Graph IDs use visible source revisions or claim identities, and edges reflect stored relation and direction. The review form shows progress and counts and asks for explicit disposition and source confirmation.
- Local Edge WALA mode uses `KNOTDEVT_E2E_WRITE=1`, `KNOTDEVT_E2E_PERSONAL=1` and `KNOTDEVT_E2E_WALA=1` with `node --env-file=../.env tests/browser.mjs`. It creates isolated synthetic accounts and imports a fixture mirroring the dashboard summary. The final run passed all five stages with the configured Gemini model, public snapshot preview, graph layout at four viewport sizes, pan/zoom/fit, branch controls, reduced motion, exact correction, critical-gap review, approved trace, receipt and 100/100 still blocked. The separate onboarding Edge test passed registration, imports and invitations.
- WALA screenshots are in the Windows temp directory: `evidence-diagram.png`, `evidence-explorer.png`, `wala-explorer-1280.png`, `wala-explorer-768.png`, `wala-explorer-390.png`, `wala-public-snapshot.png`, `corrected-claim.png`, `review.png` and `readiness-mobile.png`.
- Changed backend prompts and auditor, the dashboard extractor, the GitHub preview route/service and draft correction validation. Changed frontend generated API types, Sources, Evidence Tree/Explorer, workspace wiring, review UI and styles. Added unit regressions, a WALA fixture and browser checks. All changes remain local on the existing branch.
- Semantic entailment outside the recognized dashboard format remains a human review decision. The comparison is an on-demand public snapshot and does not convert local evidence into an imported GitHub record. The original draft was inspected read-only; the test approval belongs to the isolated WALA workspace.
- Final backend regression: 33 passed. Ruff lint and formatting, mypy (75 source files), and Alembic check passed. TypeScript, ESLint and the production build passed after the small-screen canvas adjustment. The final Edge rerun passed canvas fit checks and the complete handover flow.

## Cross-repository generalization audit

- Audited four official public GitHub issues and six unrelated meeting/conversation
  scenarios through isolated production imports and live Gemini jobs. See
  `docs/generalization-audit.md` for the expectation sheet, measurements and exact
  failures.
- Added generalized fail-closed ownership/completion rules, stage-boundary
  enforcement, exact cross-stage deduplication, task-instruction filtering, bounded
  long-source context, public snapshot assignee/closure metadata and sanitized
  provider error codes.
- Playwright ARM64 and routeFromHAR passed live claim/citation and Evidence Explorer
  checks. Full WALA body used the generic fallback successfully. pandas #71515
  remained fail-closed because duplicate quote text made its citations ambiguous.
- Two independent synthetic publications produced 100/100 assessments that remained
  blocked by reviewer-confirmed project gaps. Final regression: 48 passed; TypeScript,
  ESLint, Next build, Ruff, mypy and Alembic checks passed. Changes remain uncommitted.
