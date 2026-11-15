"""Persistent isolated local runtime; never consumes the development backlog."""

import os
import sys
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, make_url, text

DATABASE = "knotdevt_ui_839a6bd3ae9b"
QUEUE = "knotdevt-safe-local"


def configure():
    root = Path(__file__).resolve().parents[2]
    owner = make_url(dotenv_values(root / ".env")["DATABASE_URL"])
    assert (owner.host, owner.port) == ("127.0.0.1", 55432)
    url = owner.set(database=DATABASE).render_as_string(hide_password=False)
    os.environ.update(
        DATABASE_URL=url,
        RUNTIME_DATABASE_URL=url,
        LLM_PROVIDER="fake",
        JOB_QUEUE=QUEUE,
        REDIS_URL="redis://127.0.0.1:56379/14",
        PUBLIC_RESEARCH_ENABLED="false",
        ALLOWED_ORIGINS='["http://localhost:3006"]',
    )
    with create_engine(url, connect_args={"connect_timeout": 3}).connect() as conn:
        assert conn.scalar(text("SELECT current_database()")) == DATABASE
        assert conn.scalar(text("SELECT to_regclass('public.jobs')"))
    # Explicit defense against accidental use of a live adapter in this runtime.
    from app.agents import provider, research

    def forbidden(*args, **kwargs):
        raise RuntimeError("Live provider calls are disabled in the safe local runtime")

    provider.generate = forbidden
    research.research = forbidden


def main():
    configure()
    mode = sys.argv[1] if len(sys.argv) > 1 else "inspect"
    from app.workers.celery_app import EXECUTE, celery

    if mode == "worker":
        from uuid import UUID

        from sqlalchemy.orm import Session

        from app.db.agent_inputs import AgentRequest
        from app.db.session import engine
        from app.db.sources import Job
        from app.services.access import require_project

        task = celery.tasks[EXECUTE]
        original = task.run

        def guarded(job_id):
            with Session(engine()) as db:
                job = db.get(Job, UUID(job_id))
                if job is None:
                    return
                require_project(db, job.project_id, job.actor_id)
                if job.kind == "agents":
                    request = db.get(AgentRequest, job.id)
                    if request is None or request.provider != "fake":
                        raise RuntimeError("Non-deterministic job refused")
                elif job.kind not in {"import", "review_resume"}:
                    raise RuntimeError("Job kind not allowed in isolated runtime")
            return original(job_id)

        task.run = guarded
        celery.worker_main(
            [
                "worker",
                "--pool=solo",
                "--concurrency=1",
                f"--queues={QUEUE}",
                "--hostname=knotdevt-safe@%h",
                "--loglevel=INFO",
            ]
        )
    elif mode == "api":
        import uvicorn

        uvicorn.run("app.main:app", host="127.0.0.1", port=8092, access_log=False)
    elif mode == "inspect":
        inspector = celery.control.inspect(timeout=5)
        print("Isolated database:", DATABASE, "queue:", QUEUE)
        print("Ping:", inspector.ping())
        print("Registered:", inspector.registered())
        print("Queues:", inspector.active_queues())
    else:
        raise SystemExit("Use worker, api or inspect")


if __name__ == "__main__":
    main()
