from app.core.config import settings
from app.db.agent_inputs import AgentRequest
from app.db.sources import Job


def authorized(job: Job, request: AgentRequest) -> bool:
    config = settings()
    if request.provider == "fake" or config.live_ai_authorized:
        return True
    if request.provider == "openrouter":
        return (
            config.openrouter_free_job_id == job.id
            and job.queue == "knotdevt-local-new"
            and job.attempts == 0
            and request.model == "openrouter/free"
            and request.attempt_limit == 1
            and request.token_limit <= 1500
        )
    return (
        config.gemini_free_job_id == job.id
        and job.queue == "knotdevt-local-new"
        and job.attempts == 0
        and request.provider == "gemini"
        and request.model == "gemini-3.5-flash-lite"
        and request.attempt_limit == 1
        and request.token_limit <= 1500
    )
