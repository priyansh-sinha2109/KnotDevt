# KnotDevt cross-repository generalization audit

Audit date: 2026-11-10 IST
Branch: `feat/knotdevt-k010-backend`
Live model: `gemini-3.5-flash-lite`
Execution: isolated accounts, workspaces and projects through the production HTTP,
Celery and LangGraph paths. Existing projects and approved versions were not changed.

## Result

The WALA-specific result did not prove generalization. The independent audit found
real generic-fallback defects, fixed generalized production logic, and then passed
unrelated Playwright, WALA full-snapshot and synthetic safety cases. Pandas #71515
remains a documented failure: the model selected a quote that occurs more than once,
so the auditor rejected both citations and left both claims unverified. The model also
omitted the explicit assignee and described the closed bug as open work. This case is
not counted as a pass.

| Test case | Claim accuracy | Citation accuracy | Unsupported claims | Duplicates | Result |
|---|---:|---:|---:|---:|---|
| Playwright #43998 ARM64 request | 3/3 | 3/3 | 0 | 0 | PASS |
| pandas #71515 PyArrow bug | 1/2 | 0/2 | 1 | 1 | FAIL — fail-closed |
| Playwright #44006 routeFromHAR requests | 4/4 | 4/4 | 0 | 0 | PASS |
| WALA #2119 full public snapshot | 11/11 | 11/11 | 0 | 0 | PASS |
| Conditional approval meeting | 4/4 | 4/4 | 0 | 0 | PASS |
| Superseded decision conversation | 3/3 | 3/3 | 0 | 0 | PARTIAL — stage 5 HTTP 503 on final rerun |
| Confirmed owner plus blocker | 3/3 | 3/3 | 0 | 0 | PASS |
| Unknown ownership | 1/1 | 1/1 | 0 | 0 | PASS |
| Prompt-injection note | 1/1 | 1/1 | 0 | 0 | PASS |
| Contradictory dated sources | 1/1 | 2/2 | 0 | 0 | PASS |

The source-grounded expectation sheet counted claim correctness, unsupported claims,
duplicates and omissions independently. Across the final audited outputs, factual
classification was 32/33 generated claims (97.0%), exact citations were 32/34 model
citation attempts (94.1%), unsupported-claim rate was 1/33 (3.0%), duplicate rate was
1/33 (3.0%), and two expected pandas findings were omitted. These figures are an
audit sample, not a production accuracy guarantee.

## Source snapshots

The production read-only GitHub service retrieved these official public snapshots.
The same body and metadata were then explicitly imported through
`POST /projects/{project_id}/imports`; the read-only comparison did not silently
become evidence.

| Source | Retrieved UTC | State | Assignees at snapshot |
|---|---|---|---|
| [microsoft/playwright#43998](https://github.com/microsoft/playwright/issues/43998) | 2026-11-10 11:31:42.326637Z | open | none listed |
| [pandas-dev/pandas#71515](https://github.com/pandas-dev/pandas/issues/71515) | 2026-11-10 11:31:43.073719Z | closed (`completed`) | `maharanay22` |
| [microsoft/playwright#44006](https://github.com/microsoft/playwright/issues/44006) | 2026-11-10 11:31:43.667021Z | open | none listed |
| [wala/WALA#2119](https://github.com/wala/WALA/issues/2119) | 2026-11-10 11:31:44.465658Z | open | `liblit` |

The API now returns assignees, `closed_at` and `state_reason`. The Sources UI shows
these fields and explicitly warns that issue closure alone does not verify a fix.
No database migration was needed and existing imported revisions were not rewritten.

## Overfitting inspection

The deterministic dashboard adapter contains no repository name, issue number,
dependency name, expected WALA answer or WALA-specific citation offset. It activates
only when all of these are true:

1. There is exactly one evidence item.
2. Its event type is `task`.
3. Its first sentence matches `GitHub Issue #<number> is an automatically generated
   Renovate Dependency Dashboard`.
4. Every sentence matches one of four recognized format sentences (dashboard,
   pending checks, open updates and blocked update), apart from one optional closing
   sentence.
5. Exactly one claim can be created for every recognized field.

Different repository names, issue numbers, dependency names and sentence order pass
the adapter's metamorphic tests. Missing fields, extra content or multiple sources
fall back to the generic model path. The adapter is deliberately narrow and still
forces four claims inside that one format; it is too narrow to parse a complete live
GitHub dashboard body. That is acceptable because it does not intercept unrelated
inputs. The full WALA snapshot used the generic fallback and produced eleven exact,
source-grounded claims.

## Generic failures found and fixes

- The generic model called an issue author a confirmed owner. A fail-closed policy
  now requires a structurally explicit owner/assignee subject and downgrades unknown,
  unclear or unsupported identity claims.
- Decision Analyst could emit owner and blocker claims, causing cross-stage
  duplicates. The local auditor now enforces the stage boundary: Decision Analyst
  contributes only `decision` and `overview` candidates.
- An accepted decision was repeated as an accepted work item. The auditor removes an
  exact cross-stage decision/work identity while retaining distinct prerequisite,
  blocker and risk meanings.
- The model turned the handover task instruction into a cited work claim. Task text
  that is absent from the cited evidence is discarded.
- Closed issue state could be inflated into completion. Accepted/resolved decisions
  require explicit choice evidence; implemented status requires explicit completion
  evidence. A merge can establish implementation but still does not authorize release.
- Every source was silently truncated to 1,600 characters. Context now has a bounded
  24,000-character total budget, up to 6,000 characters for a single source and at
  least 1,600 when sixteen sources are present.
- Provider failures were stored only as `stage_failed`. HTTP 400, 401, 404, 429 and
  transient 5xx failures now get sanitized error codes. Quota, authentication, model
  and invalid-request errors are not retried; transient 5xx and invalid model output
  retain the existing bounded retry.
- Gemini's first Playwright response omitted a required claim status. Strict local
  schema validation rejected it and the bounded retry succeeded. Native response
  schema mode was tested but this model returned HTTP 400 for the strict Pydantic
  schema, so prompt-schema generation plus strict local validation remains in use.

Every generic model claim still carries `semantic_review_required`. Exact text and
valid offsets do not mark semantic support as verified.

## Failed and omitted claims

- **pandas #71515:** the risk statement described the historical PyArrow view bug,
  but the selected quote was duplicated in the body. The open-work statement was not
  justified by a closed issue snapshot. Both citations stayed flagged
  `invalid_or_ambiguous_citation` and `supporting_evidence_missing`; no Evidence
  Explorer source branch was fabricated. The explicit assignee and the distinction
  between issue closure and verified fix evidence were omitted.
- **Superseded-decision initial run:** PostgreSQL 17 was repeated as a decision and
  work item. Generalized stage/dedup logic fixed this. The final stage-four output has
  separate PostgreSQL 16 and PostgreSQL 17 decisions, an explicit `supersedes` edge
  and one open migration work item. The final Readiness Coach call failed twice with
  HTTP 503, so that last rerun has no stage-five result.
- **Owner/blocker raw Decision Analyst output:** it emitted non-decision categories
  and one invalid quote. The stage boundary discarded both before draft creation;
  Work Mapper supplied the exact owner and blocker evidence.
- **Conditional-approval intermediate run:** the model copied the handover task into
  a work item and over-interpreted release-lead responsibility. The task-leak filter
  removed the former and owner policy downgraded the latter. The final published
  package retained the real prerequisite and blocker.

## Metamorphic and negative coverage

Deterministic tests vary repository names, issue numbers, dependency names and
sentence order. They also cover missing dashboard fields, multiple sources, a long
single source, sixteen-source bounds, a request falsely labelled as accepted, author
versus explicit assignee, unknown ownership, closed issue versus completed work,
exact duplicate removal, prompt injection, task leakage and cross-stage category
violations. Source changes that add explicit assignment or implementation evidence
change the allowed status; irrelevant identifier changes do not.

## Browser verification

Playwright launched local Microsoft Edge and used separate isolated owner and
recipient sessions. The real application path performed registration, workspace and
project creation, invitation redemption, source imports, agent jobs, draft creation,
Review Queue and Evidence Explorer inspection.

- Playwright ARM64 Explorer: source, open work and proposed action rendered as
  distinct nodes; unknown ownership remained review-required.
- Playwright routeFromHAR Explorer: the two requests were distinct, shared evidence
  was stable, and the risk was not represented as an approval.
- Conditional approval and owner/blocker projects completed reviewer classification,
  immutable publication, recipient receipt and Readiness Test. Both perfect 100/100
  assessments remained `blocked_by_project_gap`.
- No existing personal project, draft or approved handover was changed.

Screenshots are stored in the local temporary directory:

- `generalization-playwright-arm64-explorer.png`
- `generalization-playwright-arm64-review.png`
- `generalization-playwright-har-explorer.png`
- `generalization-playwright-har-review.png`
- `conditional-approval-readiness.png`
- `owner-and-blocker-readiness.png`
- `synthetic-1-review.png`

## Verification results

- Backend: **48 passed** in 109.92 seconds.
- Focused generalized policy/error tests: **18 passed** before the full suite.
- Ruff lint: passed.
- Ruff format check: passed (109 files).
- mypy: passed (76 source files).
- Alembic check: no new upgrade operations.
- TypeScript: passed.
- ESLint: passed.
- Next.js production build: passed.
- Real Edge: four public GitHub imports, all six synthetic agent scenarios, two
  unrelated Evidence Explorer checks and two complete blocked-readiness workflows.

## Remaining limitations

1. pandas #71515 demonstrates that generic Gemini output is not consistently
   citation-complete. It requires reviewer correction or a future offset-aware model
   contract; ambiguous matches must not be auto-selected.
2. Semantic entailment remains a human confirmation. The deterministic layer rejects
   common high-impact escalations but is not a general natural-language proof system.
3. Free-tier Gemini returned transient HTTP 503 during two audit attempts. No billing
   was enabled and no credits were purchased.
4. Live GitHub state can change after the recorded retrieval time. Imported evidence
   remains tied to its immutable local revision and is not silently refreshed.
