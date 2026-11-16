"""New-job-only runtime for the original local app; live AI remains blocked."""

import os
import sys
from hashlib import sha256
from pathlib import Path


def main():
    # The user rotated the root-file credential. Do not inherit a stale terminal key.
    from dotenv import dotenv_values

    values = dotenv_values(Path(__file__).resolve().parents[2] / ".env")
    for name in ("GEMINI_API_KEY", "OPENROUTER_API_KEY"):
        if values.get(name):
            os.environ[name] = values[name]
    from sqlalchemy import make_url

    from app.core.config import settings

    config = settings()
    url = make_url(config.runtime_database_url.get_secret_value())
    if (url.host, url.port, url.database) != ("127.0.0.1", 55432, "knotdevt"):
        raise SystemExit("Expected the original local database")
    if (
        config.job_queue != "knotdevt-groq-test"
        or config.live_ai_authorized
        or config.llm_provider not in {"openai", "gemini", "openrouter", "groq"}
    ):
        raise SystemExit(
            "Expected the new-job queue with live AI authorization disabled"
        )
    config.import_job_queue = "knotdevt-imports"
    from app.agents import provider, research

    agent_root = Path(__file__).resolve().parents[1] / "app" / "agents"
    fingerprint = sha256(
        (agent_root / "graph.py").read_bytes()
        + (agent_root / "provider.py").read_bytes()
    ).hexdigest()[:16]

    def forbidden(*args, **kwargs):
        raise RuntimeError("Paid provider requests remain unauthorized")

    selected_provider = (
        "groq"
        if config.groq_free_authorized
        else "openrouter"
        if config.openrouter_free_job_id
        else "gemini"
    )
    selected_model = (
        config.groq_model
        if config.groq_free_authorized
        else "openrouter/free"
        if config.openrouter_free_job_id
        else "gemini-3.5-flash-lite"
    )
    if (
        not config.groq_free_authorized
        and config.gemini_free_job_id is None
        and config.openrouter_free_job_id is None
    ):
        provider.generate = forbidden
    else:
        import threading
        import time

        original = provider.generate
        lock = threading.Lock()
        seen = set()
        last = 0.0
        stopped = False

        def bounded(*args, **kwargs):
            nonlocal last, stopped
            with lock:
                stage = args[0]
                # The worker is long-lived, but the approved three-request
                # budget is per workflow, not per process.  A new workflow
                # always begins at the decision stage; reset state there so
                # completed jobs cannot poison subsequent jobs.  A failed
                # workflow remains stopped until its next decision stage,
                # preventing additional calls within that same run.
                if stage == "decision_analyst" and seen:
                    seen.clear()
                    stopped = False
                if (
                    stage in seen
                    or len(seen) >= 3
                    or kwargs.get("provider_name") != selected_provider
                    or args[3] != selected_model
                    or args[5] > 1500
                ):
                    raise provider.InferenceBudgetExceededError(
                        "Single-workflow authorization budget exhausted"
                    )
                if stopped:
                    raise provider.ParallelStageCancelledError(
                        "Parallel stage cancelled after a peer stage failed"
                    )
                remaining = 61 - (time.monotonic() - last)
                if remaining > 0:
                    time.sleep(remaining)
                seen.add(stage)
                import logging

                logging.getLogger(__name__).info(
                    "authorized_provider_request stage=%s request=%s", stage, len(seen)
                )
                last = time.monotonic()
                try:
                    result = original(*args, **kwargs)
                    if stage == "readiness_coach":
                        seen.clear()
                        stopped = False
                    return result
                except Exception:
                    stopped = True
                    raise

        provider.generate = bounded
    research.research = forbidden
    from app.workers.celery_app import celery

    mode = sys.argv[1] if len(sys.argv) > 1 else "inspect"
    if mode == "worker":
        print(f"worker_code_fingerprint={fingerprint}", flush=True)
        celery.worker_main(
            [
                "worker",
                "--pool=solo",
                "--concurrency=1",
                f"--queues={config.job_queue}",
                "--hostname=knotdevt-local@%h",
                "--loglevel=INFO",
            ]
        )
    elif mode == "api":
        import uvicorn

        uvicorn.run("app.main:app", host="127.0.0.1", port=8080, access_log=False)
    elif mode == "beat":
        directory = Path(os.environ["LOCALAPPDATA"]) / "KnotDevt" / "logs"
        directory.mkdir(parents=True, exist_ok=True)
        celery.start(
            ["beat", "--loglevel=INFO", "--schedule", str(directory / "local-beat")]
        )
    elif mode == "inspect":
        inspect = celery.control.inspect(timeout=3)
        print("Queue:", config.job_queue)
        print("Ping:", inspect.ping())
        print("Registered:", inspect.registered())
        print("Queues:", inspect.active_queues())
    else:
        raise SystemExit("Use worker, beat, api or inspect")


if __name__ == "__main__":
    main()
