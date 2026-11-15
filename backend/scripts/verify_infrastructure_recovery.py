"""Opt-in real process/container faults against newly created isolated resources."""

import os
import secrets
import subprocess
import sys
import time
import tempfile
from pathlib import Path
from uuid import UUID, uuid4


def docker(*args: str) -> str:
    return subprocess.check_output(["docker", *args], text=True).strip()


def wait(check, seconds=40):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if check():
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise AssertionError("Isolated recovery condition timed out")


def main():
    if os.environ.get("KNOTDEVT_ISOLATED_FAULT_TEST") != "1":
        raise SystemExit(
            "Set KNOTDEVT_ISOLATED_FAULT_TEST=1 to create isolated containers"
        )
    suffix = uuid4().hex[:10]
    postgres, redis = f"knotdevt-fault-pg-{suffix}", f"knotdevt-fault-redis-{suffix}"
    created = []
    workers = []
    root = Path(tempfile.gettempdir()) / f"knotdevt-fault-test-{suffix}"
    root.mkdir()
    os.environ["POSTGRES_PASSWORD"] = secrets.token_hex(24)
    try:
        for name, image, port in (
            (postgres, "postgres:17-alpine", 5432),
            (redis, "redis:7-alpine", 6379),
        ):
            args = ["run", "-d", "--name", name, "-p", f"127.0.0.1::{port}"]
            if name == postgres:
                args += ["-e", "POSTGRES_PASSWORD", "-e", "POSTGRES_DB=knotdevt_fault"]
            docker(*args, image)
            created.append(name)
        pg_port = docker("port", postgres, "5432/tcp").rsplit(":", 1)[1]
        redis_port = docker("port", redis, "6379/tcp").rsplit(":", 1)[1]
        url = ("postgresql+psycopg://postgres:" + os.environ["POSTGRES_PASSWORD"]
               + f"@127.0.0.1:{pg_port}/knotdevt_fault")
        os.environ.update(
            DATABASE_URL=url,
            RUNTIME_DATABASE_URL=url,
            REDIS_URL=f"redis://127.0.0.1:{redis_port}/0",
            LLM_PROVIDER="fake",
            SESSION_SIGNING_SECRET=secrets.token_hex(32),
        )
        from sqlalchemy import create_engine, select, text
        from sqlalchemy.orm import Session

        owner = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 2})

        def connected():
            with owner.connect() as conn:
                return conn.scalar(text("SELECT 1")) == 1

        wait(connected)
        from alembic.config import Config

        from alembic import command

        command.upgrade(Config("alembic.ini"), "head")
        from scripts.setup_checkpoints import main as setup

        setup()
        from app.db.handover import Version
        from app.db.identity import Role
        from app.db.session import engine
        from app.db.sources import Job
        from app.workers.celery_app import celery
        from tests.support import client_for, create_demo_draft, project_with

        project, [(_, reviewer), (recipient_id, _)] = project_with(
            Role.REVIEWER, Role.RECIPIENT
        )
        with client_for(reviewer) as client:
            draft = create_demo_draft(client, project, recipient_id)
            approved = client.post(
                f"/api/v1/drafts/{draft['id']}/approve",
                json={
                    "expected_revision": draft["revision"],
                    "rubric": draft["proposed_rubric"],
                },
            )
            assert approved.status_code == 201
            version_id = UUID(approved.json()["id"])
            with Session(engine()) as db:
                resume_id = db.get(Version, version_id).resume_job_id
            marker = root / "checkpoint-committed"
            pause_code = ("def pause(db,job):\n original(db,job)\n "
                          + f"Path({marker.as_posix()!r}).touch()\n time.sleep(120)")
            bootstrap = (
                "from app.workers import celery_app as w; "
                "from pathlib import Path; import time; "
                "original=w.resume_review; "
                + f"exec({pause_code!r}); "
                + "w.resume_review=pause; "
                "w.celery.worker_main(['worker','--pool=solo','--loglevel=WARNING'])"
            )

            def worker(code=None):
                log = (root / f"worker-{len(workers)}.log").open("w")
                args = (
                    [sys.executable, "-c", code]
                    if code
                    else [
                        sys.executable,
                        "-m",
                        "celery",
                        "-A",
                        "app.workers.celery_app:celery",
                        "worker",
                        "--pool=solo",
                        "--loglevel=WARNING",
                    ]
                )
                process = subprocess.Popen(args, stdout=log, stderr=log)
                workers.append(process)
                return process

            doomed = worker(bootstrap)
            celery.send_task("knotdevt.execute", args=[str(resume_id)])
            wait(marker.exists)
            subprocess.run(["taskkill", "/PID", str(doomed.pid), "/T", "/F"], check=True, capture_output=True)
            doomed.wait(timeout=10)
            print(
                "PASS: hard Celery process termination after checkpoint commit",
                flush=True,
            )
            docker("stop", postgres)
            response = client.get("/health/ready")
            assert response.status_code == 503 and not response.json()["postgres"]
            docker("start", postgres)
            wait(connected)
            print("PostgreSQL restarted and reachable", flush=True)
            engine().dispose()
            docker("stop", redis)
            response = client.get("/health/ready")
            assert response.status_code == 503 and not response.json()["redis"]
            docker("start", redis)
            def ready():
                response = client.get("/health/ready")
                print("Isolated readiness:", response.json(), flush=True)
                return response.status_code == 200
            wait(ready)
            print(
                "PASS: isolated PostgreSQL/Redis stop/start and readiness recovery",
                flush=True,
            )
            worker()
            celery.send_task("knotdevt.execute", args=[str(resume_id)])

            def reconciled():
                with Session(engine()) as db:
                    return db.get(Job, resume_id).state == "succeeded"

            wait(reconciled)
            celery.send_task("knotdevt.execute", args=[str(resume_id)])
            time.sleep(2)
            with Session(engine()) as db:
                assert (
                    len(
                        db.scalars(
                            select(Version).where(Version.draft_id == UUID(draft["id"]))
                        ).all()
                    )
                    == 1
                )
            assert (
                client.get(f"/api/v1/versions/{version_id}").json() == approved.json()
            )
            print(
                "PASS: reconciliation after restarts, duplicates, one unchanged version",
                flush=True,
            )
    finally:
        for process in workers:
            if process.poll() is None:
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
                process.wait(timeout=10)
        for name in created:
            docker("stop", name)
        print(
            "Isolated containers stopped and retained; no databases or volumes deleted.",
            flush=True,
        )


if __name__ == "__main__":
    main()
