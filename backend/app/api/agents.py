from uuid import UUID

from fastapi import APIRouter

from app.api.dependencies import DB, Actor
from app.schemas.agents import AgentInput, RunView
from app.schemas.sources import JobView
from app.services.access import require_project
from app.services.agents import inspect_runs, queue_agents
from app.services.jobs import job_view

router = APIRouter(tags=["agents"])


@router.post("/projects/{project_id}/agent-jobs", status_code=202)
def create(project_id: UUID, body: AgentInput, identity: Actor, db: DB) -> JobView:
    access = require_project(db, project_id, identity.user.id)
    return job_view(queue_agents(db, access, body))


@router.get("/jobs/{job_id}/runs")
def runs(job_id: UUID, identity: Actor, db: DB) -> list[RunView]:
    return inspect_runs(db, job_id, identity.user.id)
