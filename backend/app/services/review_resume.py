from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.checkpoints import checkpoints
from app.agents.graph import RunConfig, run_graph
from app.db.agent_inputs import AgentRequest
from app.db.handover import Draft, Version
from app.db.sources import Job
from app.services.imports import JobFailure


def resume_review(db: Session, job: Job) -> None:
    agent_job = db.scalar(
        select(Draft.agent_job_id)
        .join(Version, Version.draft_id == Draft.id)
        .where(Version.resume_job_id == job.id, Version.project_id == job.project_id)
    )
    if agent_job is None:
        raise JobFailure("review_checkpoint_unavailable")
    request = db.get(AgentRequest, agent_job)
    if request is None:
        raise JobFailure("review_checkpoint_unavailable")
    cfg = RunConfig(
        agent_job,
        request.provider,
        request.model,
        request.attempt_limit,
        request.timeout_seconds,
        request.token_limit,
    )
    with checkpoints() as saver:
        run_graph(cfg, None, saver, approval=True)
