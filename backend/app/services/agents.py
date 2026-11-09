import hashlib
from typing import Literal, cast
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.agents.checkpoints import checkpoints
from app.agents.graph import RunConfig, run_graph
from app.agents.instructions import TOOLS
from app.core.config import settings
from app.db.agent_inputs import AgentRequest
from app.db.evidence import AgentRun
from app.db.sources import Job, Source, SourceRevision
from app.repositories.evidence import get_visible_revision
from app.repositories.sources import can_read_source, current_revision_id
from app.schemas.agents import (
    AgentInput,
    AuditOutput,
    ContextBundle,
    ContextItem,
    DecisionOutput,
    RubricProposal,
    RunOutput,
    RunView,
    Stage,
    WorkOutput,
)
from app.services.access import (
    EDITORS,
    REVIEWERS,
    ProjectAccess,
    audit,
    require_project,
)
from app.services.imports import JobFailure

MODELS: dict[Stage, type[RunOutput]] = {
    "context_collector": ContextBundle,
    "decision_analyst": DecisionOutput,
    "work_mapper": WorkOutput,
    "evidence_auditor": AuditOutput,
    "readiness_coach": RubricProposal,
}


def queue_agents(db: Session, access: ProjectAccess, data: AgentInput) -> Job:
    access.require(EDITORS)
    config = settings()
    if config.llm_provider == "gemini" and config.gemini_api_key is None:
        raise HTTPException(503, "Model provider is unavailable")
    for user_id in data.audience:
        require_project(db, access.project.id, user_id)
    query = (
        select(Source, SourceRevision)
        .join(SourceRevision, SourceRevision.id == current_revision_id())
        .where(Source.project_id == access.project.id)
        .where(*(can_read_source(user) for user in {access.user_id, *data.audience}))
        .order_by(
            case((Source.original_id.in_(data.source_ids), 0), else_=1),
            SourceRevision.event_at.desc(),
            Source.id,
        )
        .limit(16)
    )
    rows = db.execute(query).all()
    if not rows:
        raise HTTPException(409, "No evidence available for the selected audience")

    job = Job(
        project_id=access.project.id,
        actor_id=access.user_id,
        kind="agents",
        input_hash=hashlib.sha256(data.model_dump_json().encode()).hexdigest(),
    )
    db.add(job)
    db.flush()
    db.add(
        AgentRequest(
            job_id=job.id,
            input=data.model_dump(mode="json"),
            revision_ids=[str(row[1].id) for row in rows],
            policy_revisions={str(row[0].id): row[0].policy_revision for row in rows},
            provider=config.llm_provider,
            model=config.llm_model,
            attempt_limit=config.agent_attempts,
            timeout_seconds=config.agent_timeout_seconds,
            token_limit=config.agent_token_limit,
        )
    )
    audit(db, access.user_id, "agents.queued", project=access.project, target_id=job.id)
    db.commit()
    return job


def load_context(
    db: Session,
    job: Job,
    request: AgentRequest,
    user_id: UUID,
    *,
    fresh: bool,
) -> ContextBundle:
    inputs = AgentInput.model_validate(request.input)
    evidence = []
    missing = set(inputs.source_ids)
    for revision_id in request.revision_ids:
        row = get_visible_revision(db, job.project_id, user_id, UUID(revision_id))
        if row is None:
            raise HTTPException(404, "Agent evidence unavailable")
        source, revision = row
        if fresh and (
            source.policy_revision != request.policy_revisions[str(source.id)]
            or db.scalar(select(current_revision_id()).where(Source.id == source.id))
            != revision.id
        ):
            raise HTTPException(409, "Agent evidence changed")
        evidence.append(
            ContextItem(
                revision_id=revision.id,
                source_id=source.original_id,
                event_type=revision.event_type,
                excerpt=revision.excerpt[:1600],
                event_time=revision.event_at.isoformat(),
                related_ids=revision.related_ids,
            )
        )
        missing.update(revision.related_ids)
    counts = {key: sum(item.source_id == key for item in evidence) for key in missing}
    return ContextBundle(
        task=inputs.task,
        evidence=evidence,
        unresolved_ids=sorted(key for key, count in counts.items() if count != 1),
    )


def run_agents(db: Session, job: Job) -> None:
    try:
        access = require_project(db, job.project_id, job.actor_id)
        access.require(EDITORS)
        request = db.get(AgentRequest, job.id)
        if request is None:
            raise JobFailure("agent_request_unavailable")
        inputs = AgentInput.model_validate(request.input)
        bundle = load_context(db, job, request, job.actor_id, fresh=True)
        for user_id in inputs.audience:
            require_project(db, job.project_id, user_id)
            load_context(db, job, request, user_id, fresh=True)
    except HTTPException:
        raise JobFailure("agent_evidence_changed") from None
    cfg = RunConfig(
        job.id,
        request.provider,
        request.model,
        request.attempt_limit,
        request.timeout_seconds,
        request.token_limit,
    )
    with checkpoints() as saver:
        run_graph(cfg, bundle, saver)
    audit(
        db,
        job.actor_id,
        "agents.awaiting_review",
        project=access.project,
        target_id=job.id,
    )


def inspect_runs(db: Session, job_id: UUID, user_id: UUID) -> list[RunView]:
    job = db.get(Job, job_id)
    if job is None or job.kind != "agents":
        raise HTTPException(404, "Agent job not found")
    try:
        access = require_project(db, job.project_id, user_id)
    except HTTPException:
        raise HTTPException(404, "Agent job not found") from None
    if access.role not in EDITORS or (
        job.actor_id != user_id and access.role not in REVIEWERS
    ):
        raise HTTPException(404, "Agent job not found")
    request = db.get(AgentRequest, job.id)
    if request is None:
        raise HTTPException(404, "Agent job not found")
    load_context(db, job, request, user_id, fresh=False)
    rows = db.scalars(
        select(AgentRun)
        .where(AgentRun.job_id == job.id)
        .order_by(AgentRun.created_at, AgentRun.role, AgentRun.attempt)
    )
    results = []
    for row in rows:
        role = cast(Stage, row.role)
        results.append(
            RunView(
                id=row.id,
                role=role,
                attempt=row.attempt,
                model=row.model,
                prompt_version=row.prompt_version,
                status=cast(Literal["running", "succeeded", "failed"], row.status),
                output=(
                    MODELS[role].model_validate(row.output)
                    if row.output is not None
                    else None
                ),
                timeout_seconds=row.timeout_seconds,
                attempt_limit=row.attempt_limit,
                tools=TOOLS[role],
                error_code=row.error_code,
            )
        )
    return results
