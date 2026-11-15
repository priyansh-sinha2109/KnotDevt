from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import Field

from app.agents.research import research
from app.api.dependencies import DB, Actor
from app.core.config import settings
from app.schemas.agents import AgentInput, RunView
from app.schemas.sources import JobView, StrictModel
from app.services.access import EDITORS, audit, require_project
from app.services.agents import inspect_runs, queue_agents
from app.services.jobs import get_job

router = APIRouter(tags=["agents"])


class PublicResearchInput(StrictModel):
    query: Annotated[str, Field(min_length=1, max_length=500)]
    domains: Annotated[list[str], Field(min_length=1, max_length=5)]


@router.post("/projects/{project_id}/public-research")
def public_research(
    project_id: UUID, body: PublicResearchInput, identity: Actor, db: DB
) -> dict[str, Any]:
    access = require_project(db, project_id, identity.user.id)
    access.require(EDITORS)
    if not settings().public_research_enabled:
        raise HTTPException(
            503, "Public research is disabled pending operator authorization"
        )
    try:
        result = research(body.query, body.domains, permitted=True)
    except ValueError:
        raise HTTPException(
            422, "Public research request or configuration is invalid"
        ) from None
    except Exception:
        raise HTTPException(503, "Public research temporarily unavailable") from None
    audit(db, identity.user.id, "research.previewed", project=access.project)
    db.commit()
    return result


@router.post("/projects/{project_id}/agent-jobs", status_code=202)
def create(project_id: UUID, body: AgentInput, identity: Actor, db: DB) -> JobView:
    access = require_project(db, project_id, identity.user.id)
    job = queue_agents(db, access, body)
    return get_job(db, job.id, identity.user.id)


@router.get("/jobs/{job_id}/runs")
def runs(job_id: UUID, identity: Actor, db: DB) -> list[RunView]:
    return inspect_runs(db, job_id, identity.user.id)
