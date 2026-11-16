"""Verified product knowledge for the KnotDevt guide chatbot.

Every entry is grounded in the actual K0.1.0 application: routes, backend
endpoints, roles, and the five-agent workflow.  Nothing here describes a
planned or unimplemented feature.  The chatbot system instruction includes this
text so the model can answer product questions without inventing capabilities.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Public overview
# ---------------------------------------------------------------------------

OVERVIEW = """\
KnotDevt preserves the reasoning behind a project when responsibility moves to \
someone new.  It brings permitted issues, tasks, meeting notes, and conversation \
records into one traceable thread, then turns that thread into a reviewable \
handover.  AI proposes threads; deterministic checks and a human reviewer decide \
what can be published.  Each approved handover keeps an immutable version, a \
Context Trace, a critical-gap review, and a recipient Readiness Test.  A model \
suggestion is never treated as a verified fact merely because a model stated it.\
"""

# ---------------------------------------------------------------------------
# Roles and permissions
# ---------------------------------------------------------------------------

ROLES = """\
KnotDevt uses four roles inside a workspace:

- Administrator — creates workspaces and projects, invites teammates, assigns \
project roles, and can import sources and run the AI workflow.
- Reviewer — can import sources, run the five-agent workflow, inspect claims and \
citations, correct unsupported claims, complete the critical-gap review, and \
publish an immutable handover version.  An administrator is also a reviewer.
- Contributor — can import sources and run the AI workflow.  Contributors cannot \
review claims or publish handovers.
- Recipient — can view published handover versions, open the Context Trace, \
complete the Readiness Test, and acknowledge receipt.  Recipients cannot import \
sources, run workflows, or publish versions.

Editors are administrators, reviewers, and contributors.  A recipient is not an \
editor.  Project access is enforced server-side; a user who is not a project \
member cannot see project data.\
"""

# ---------------------------------------------------------------------------
# Workspace and project creation
# ---------------------------------------------------------------------------

WORKSPACE_PROJECTS = """\
To start using KnotDevt:

1. Register an account or sign in.
2. Create a workspace (the first user in a workspace becomes its administrator).
3. Create a project inside the workspace.
4. Invite an existing teammate to the workspace and assign a project role.

Workspaces and projects are created from the Projects view in the workspace \
dashboard.  A workspace administrator can create projects.  Teammates join a \
workspace by redeeming a one-time invitation code.  After joining, an \
administrator assigns them a project role (reviewer, contributor, or recipient).\
"""

# ---------------------------------------------------------------------------
# Invitations and recipient assignment
# ---------------------------------------------------------------------------

INVITATIONS = """\
KnotDevt uses private one-time invitation codes.  An administrator generates an \
invitation, shares the 43-character code with the teammate, and the teammate \
redeems it from the workspace dashboard to join the workspace.

To assign a recipient to a project, a workspace administrator adds a workspace \
member as a project recipient.  Only active workspace members can be assigned \
as recipients.  A person who already has a different project role cannot be \
made a recipient for that project.\
"""

# ---------------------------------------------------------------------------
# Source imports
# ---------------------------------------------------------------------------

SOURCES = """\
Sources are permitted project evidence imported into KnotDevt.  Two import \
formats are supported:

1. Issue events (kind "issue-events") — proposals, implementations, tasks, and \
comments, each with an author, event time, reference URL or fixture identifier, \
text, optional related IDs, and an access policy.
2. Conversation notes (kind "conversation-notes") — decisions, meetings, and \
messages, with the same fields.

Each import creates immutable source revisions.  A revision stores an excerpt, \
author, event type, reference, and content hash.  Revisions cannot be modified \
after import; a new import creates a new revision.  Source access rules control \
which users can see which sources.  The access policy can be "project" (visible \
to project members) or other configured policies.

Automatic Slack, Notion, Figma, Discord, PDF, and private GitHub ingestion are \
NOT available.  The public GitHub issue preview is read-only comparison; it is \
not evidence import unless a supported source record is created.\
"""

# ---------------------------------------------------------------------------
# Five-agent workflow
# ---------------------------------------------------------------------------

FIVE_AGENTS = """\
KnotDevt runs a five-stage LangGraph workflow:

1. Context Collector — collects bounded source revisions and resolves exact \
references.  This stage runs first and provides evidence to the next stages.

2. Decision Analyst — identifies decisions (proposed, accepted, implemented, \
rejected, or conflicting).  A merge does not authorize release.  Issue closure \
is repository state and does not prove a fix shipped.  Preserves unresolved \
authority and missing rationale.

3. Work Mapper — identifies work items, documented owners and contacts, \
prerequisites, blockers, risks, next actions, and recurring-problem \
candidates.  Preserves explicit ownership gaps.  An issue author is not an \
owner unless assignment is explicit.

4. Evidence Auditor — verifies exact source IDs, spans, and provenance.  Flags \
missing, contradictory, or unsupported claims for human review.

5. Readiness Coach — proposes four safe multiple-choice rehearsal questions for \
the task, one per dimension (action, prerequisites, evidence, escalation), with \
a zero-based correct choice, explanation, and evidence revision references.

Decision Analyst and Work Mapper run in parallel after the Context Collector.  \
The Evidence Auditor runs after both complete.  The Readiness Coach runs after \
the auditor.  The workflow pauses at a human review checkpoint; a completed AI \
job is not an approved handover.\
"""

# ---------------------------------------------------------------------------
# Evidence Explorer
# ---------------------------------------------------------------------------

EVIDENCE_EXPLORER = """\
The Evidence Explorer shows source-linked claims with exact citation spans.  \
Each claim points to a permitted source revision with a verbatim quote and \
zero-based Unicode start and end offsets.  The explorer renders an evidence \
graph using React Flow and ELK.js.  Reviewers and recipients can inspect \
claims, citations, and the relationships between claims.\
"""

# ---------------------------------------------------------------------------
# Human review and publishing
# ---------------------------------------------------------------------------

REVIEW_PUBLISH = """\
After the five-agent workflow completes, a reviewer inspects the proposed claims:

1. Review the claim list in the Review Queue.
2. Verify each claim's citations against the source excerpts.
3. Correct unsupported or inaccurate claims.
4. Complete the Critical-gap Review by giving each gap a disposition \
(blocking, unverified, or resolved) backed by evidence.
5. Confirm the source snapshot and rubric.
6. Publish the immutable handover version.

A published handover version is immutable.  If sources change after publishing, \
the version becomes stale and a new version must be published.  A score of \
100/100 on the Readiness Test cannot override unresolved project blockers.\
"""

# ---------------------------------------------------------------------------
# Readiness assessment
# ---------------------------------------------------------------------------

READINESS = """\
After a handover version is published, the recipient can:

1. Open the Context Trace to review the approved handover content.
2. Complete the Readiness Test — a set of multiple-choice questions generated by \
the Readiness Coach, covering four dimensions: action, prerequisites, evidence, \
and escalation.
3. Write an explanation for each question.
4. An advisory may be generated to offer short feedback on the explanation.  \
The advisory does not grade, assign a score, declare readiness, or override \
any safety gate.  The reviewer can correct the advisory.
5. The reviewer reviews the attempt and can approve or reject it.
6. The recipient acknowledges receipt.

A readiness score of 100/100 does not override unresolved critical blockers.\
"""

# ---------------------------------------------------------------------------
# Workflow states
# ---------------------------------------------------------------------------

WORKFLOW_STATES = """\
Jobs (workflow runs) have these states:

- queued — the job is accepted and waiting for a Celery worker.
- running — a worker is executing the five-agent workflow.
- succeeded — all stages completed (but human review is still required).
- failed — one or more stages failed.  The error_code field explains why.

Agent runs (individual stage attempts) also track state: running, succeeded, \
or failed, with an error_code.  A failed stage may be retried a bounded number \
of times.  Transient failures (timeouts, temporary unavailability) allow one \
retry; permanent failures (quota exhaustion, authentication failure, invalid \
output) do not retry.

A completed AI job is NOT an approved handover.  The workflow pauses at the \
human review checkpoint and only a reviewer's explicit approval publishes a \
version.\
"""

# ---------------------------------------------------------------------------
# Navigation routes
# ---------------------------------------------------------------------------

ROUTES = {
    "landing": {"path": "/", "label": "Landing page", "auth": "public"},
    "login": {"path": "/login", "label": "Sign in or register", "auth": "public"},
    "workspace": {
        "path": "/app",
        "label": "Workspace dashboard",
        "auth": "authenticated",
    },
    "overview": {
        "path": "/app?view=overview",
        "label": "Overview",
        "auth": "authenticated",
    },
    "projects": {
        "path": "/app?view=projects",
        "label": "Projects",
        "auth": "authenticated",
    },
    "sources": {
        "path": "/app?view=sources",
        "label": "Sources",
        "auth": "project member (editor)",
    },
    "ai_workflow": {
        "path": "/app?view=agents",
        "label": "AI Workflow",
        "auth": "project member (editor)",
    },
    "evidence": {
        "path": "/app?view=evidence",
        "label": "Evidence Explorer",
        "auth": "project member (reviewer or recipient)",
    },
    "review": {
        "path": "/app?view=review",
        "label": "Review Queue",
        "auth": "project member (reviewer)",
    },
    "versions": {
        "path": "/app?view=versions",
        "label": "Handover Versions",
        "auth": "project member (reviewer or recipient)",
    },
    "readiness": {
        "path": "/app?view=readiness",
        "label": "Readiness",
        "auth": "project member (reviewer or recipient)",
    },
}

# ---------------------------------------------------------------------------
# Limitations (what does NOT exist)
# ---------------------------------------------------------------------------

LIMITATIONS = """\
The following are NOT available in KnotDevt K0.1.0 and must not be claimed as \
existing features:

- Automatic Slack, Notion, Figma, Discord, PDF, or private GitHub ingestion.
- Voice features.
- Project Help Mode (recipient Q&A against handover evidence) — this is an \
architectural boundary reserved for K0.2.0 and is not yet available.  The guide \
chatbot explains the platform and helps with navigation; it does not answer \
questions about specific project evidence.
- A model suggestion is never a verified fact.
- Missing evidence is not proof that an event never occurred.
- Exact quote matching does not prove semantic support.
- Unknown ownership, approvals, and contacts remain explicitly uncertain.
- Closed issue state is not evidence that a fix was implemented.
"""

# ---------------------------------------------------------------------------
# Assembled knowledge text injected into the system instruction
# ---------------------------------------------------------------------------

KNOWLEDGE_TEXT = f"""\
{OVERVIEW}

ROLES AND PERMISSIONS
{ROLES}

WORKSPACE AND PROJECT CREATION
{WORKSPACE_PROJECTS}

INVITATIONS AND RECIPIENT ASSIGNMENT
{INVITATIONS}

SOURCE IMPORTS
{SOURCES}

FIVE-AGENT WORKFLOW
{FIVE_AGENTS}

EVIDENCE EXPLORER
{EVIDENCE_EXPLORER}

HUMAN REVIEW AND PUBLISHING
{REVIEW_PUBLISH}

READINESS ASSESSMENT
{READINESS}

WORKFLOW STATES
{WORKFLOW_STATES}

LIMITATIONS
{LIMITATIONS}
"""


def route_for(view: str) -> dict[str, str] | None:
    """Return the route metadata for a known view, or ``None`` if unknown."""
    return ROUTES.get(view)
