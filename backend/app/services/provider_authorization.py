from app.core.config import settings
from app.db.agent_inputs import AgentRequest
from app.db.sources import Job

GROQ_TEST_QUEUES = {"knotdevt-local-new", "knotdevt-groq-test"}


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
    if request.provider == "groq":
        return (
            config.groq_free_authorized
            and (
                job.queue in GROQ_TEST_QUEUES
                or (
                    job.queue == config.groq_authorized_queue
                    and config.groq_free_job_id == job.id
                )
            )
            and job.attempts == 0
            and request.model == config.groq_model
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
