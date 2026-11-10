# KnotDevt state-machine map

KnotDevt has several workflows whose states were historically distributed across
database rows, service guards, and UI conditions. This document identifies the
authoritative state for each workflow. Product copy may humanize these values,
but it must never invent a transition or infer readiness from a score.

| Machine | States / phases | Transition authority | Safety invariant |
| --- | --- | --- | --- |
| Browser session | signed out, authenticating, signed in, expired/revoked | authentication service and server-side session row | A UI state never grants access; a 401 returns the browser to sign-in. |
| Workspace/project access | absent, member, recipient, reviewer, administrator | membership services and RBAC checks | Discovery and every resource operation re-check membership. |
| One-time invitation | issued, accepted, expired/invalid | invitation service and Redis one-time record | A code is scoped, expires, and can be redeemed once; acceptance does not bypass membership policy. |
| Source lifecycle | imported, duplicate, revised, restricted, deleted | import and source-policy services | Every claim points to an immutable revision; restricted content is filtered before graph/API presentation. |
| Background job | queued, waiting retry, succeeded, failed | worker and job service | Transient failures are bounded; completed agent stages are reused; failure is never presented as success. |
| Five-agent execution | collect, parallel decision/work analysis, audit, coaching, human review | LangGraph plus persisted `AgentRun` rows | A model output cannot publish itself. Human review is a separate checkpoint. |
| Agent stage attempt | running, succeeded, failed | agent runner | Attempts are append-only evidence of execution; a successful earlier stage may be resumed safely. |
| Draft review | generated, corrected, review stale, gap review confirmed, approved | draft, correction, and critical-gap services | Claim/source changes invalidate confirmations. Approved versions remain immutable. |
| Critical gap | blocking, unverified, resolved, non-blocking | reviewer confirmation plus deterministic validation | Unknown critical dependencies fail closed; a high assessment score cannot override them. |
| Handover version | approved, stale, unavailable, withdrawn | version-state service | Recipients only consume an authorized immutable snapshot. |
| Readiness package | ready, blocked by project gap, access review required, stale/review required | readiness packaging service | Package status and recipient score are independent gates. |
| Recipient assessment | ready for scoped task, needs guided practice, blocked by project gap, access review required, stale/review required | readiness assessment and package gate | The package gate wins over a 100/100 assessment. |
| Assessment review | pending, reviewed, withheld | authorized reviewer | Recipient answers do not self-approve restricted or blocked work. |
| Receipt | unacknowledged, acknowledged | receipt service | Acknowledgement records access to a specific version; it does not change readiness. |
| Evidence Explorer | closed/open, loading/ready/error, focused node, expanded branches, relationship filters | client presentation over authorized API data | Visual state cannot reveal filtered nodes, labels, counts, or edges. |
| Public motion | first visit/introduced, transitioning/settled, full/reduced motion | client preference and persistent transition controller | Animation never blocks navigation or form submission and respects reduced motion. |

## Explicit background-job projection

The database-compatible `state` remains `queued`, `succeeded`, or `failed`.
`JobView.phase` is the user- and agent-facing projection:

```text
queued (attempt 0) ────────────────> succeeded ──> awaiting_human_review (agent jobs)
       │                                  └─────> succeeded (other jobs)
       └─ transient failure ─> waiting_retry ──> queued/resumed
                                      └────────> failed (retry limit)
```

`next_action` is deliberately small: `wait`, `review`, `inspect_error`, or
`none`. This gives the frontend and API consumers one shared interpretation
without changing the persisted state or exposing worker internals in normal UI.

## Development rules

1. Add a state or transition to the backend contract before adding UI logic for it.
2. Keep persisted state backward compatible; expose derived phases when a richer
   product explanation is needed.
3. Every fail-open transition needs an explicit test. Security, evidence,
   critical-gap, and readiness uncertainty must fail closed.
4. Use backend status for actions and permissions. UI badges and animations are
   presentation only.
5. Agent consumers should use `phase` and `next_action`, not infer workflow
   meaning from error text or claim scores.
