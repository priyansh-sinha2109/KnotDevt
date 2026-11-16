"""Create a fresh local database and verify the built UI with a private fake queue."""

import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from dotenv import dotenv_values
from sqlalchemy import create_engine, make_url, text


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    root = Path(__file__).resolve().parents[2]
    owner = make_url(dotenv_values(root / ".env")["DATABASE_URL"])
    assert (owner.host, owner.port) == ("127.0.0.1", 55432)
    suffix = uuid4().hex[:12]
    name = "knotdevt_ui_" + suffix
    with create_engine(
        owner.set(database="postgres"), isolation_level="AUTOCOMMIT"
    ).connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = owner.set(database=name).render_as_string(hide_password=False)
    api_port, site_port = port(), port()
    os.environ.update(
        DATABASE_URL=url,
        RUNTIME_DATABASE_URL=url,
        LLM_PROVIDER="fake",
        JOB_QUEUE="ui-fake-" + suffix,
        REDIS_URL="redis://127.0.0.1:56379/14",
        ALLOWED_ORIGINS=json.dumps([f"http://localhost:{site_port}"]),
        SESSION_SIGNING_SECRET=secrets.token_hex(32),
        PUBLIC_RESEARCH_ENABLED="false",
    )
    from alembic.config import Config

    from alembic import command

    command.upgrade(Config(str(root / "backend/alembic.ini")), "head")
    from scripts.setup_checkpoints import main as checkpoints

    checkpoints()
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.db.evidence import AgentRun
    from app.db.handover import Draft
    from app.db.identity import Role
    from app.db.session import engine
    from app.db.sources import Job
    from tests.integration.test_auth import PASSWORD
    from tests.support import FIXTURES, client_for, project_with

    project, [(_, reviewer), (recipient, _)] = project_with(
        Role.REVIEWER, Role.RECIPIENT
    )
    temporary = Path(tempfile.mkdtemp(prefix="knotdevt-ui-"))
    processes = []

    def start(args, cwd):
        log = (temporary / f"process-{len(processes)}.log").open("w")
        process = subprocess.Popen(args, cwd=cwd, stdout=log, stderr=log)
        processes.append(process)
        return process

    try:
        worker = (
            "from app.agents import provider; "
            "provider.generate=lambda *a,**k: (_ for _ in ()).throw("
            "RuntimeError('Live calls forbidden')); "
            "from app.workers.celery_app import celery; "
            f"celery.worker_main(['worker','--pool=solo','--queues={os.environ['JOB_QUEUE']}','--loglevel=ERROR'])"
        )
        start([sys.executable, "-c", worker], root / "backend")
        start(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(api_port),
            ],
            root / "backend",
        )
        handler = (
            "class Handler(SimpleHTTPRequestHandler):\n"
            " def do_GET(self):\n"
            '  path=self.path.split("?")[0]\n'
            '  if Path("."+path+".html").is_file(): self.path=path+".html"\n'
            "  super().do_GET()"
        )
        server = (
            "from http.server import SimpleHTTPRequestHandler,HTTPServer; "
            "from pathlib import Path; "
            + f"exec({handler!r}); "
            + f"HTTPServer(('127.0.0.1',{site_port}),Handler).serve_forever()"
        )
        start([sys.executable, "-c", server], root / "frontend/out")
        for _ in range(60):
            try:
                if (
                    httpx.get(
                        f"http://localhost:{api_port}/health", timeout=1
                    ).status_code
                    == 200
                ):
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        with client_for(reviewer) as client:
            workspace = client.get(f"/api/v1/projects/{project}").json()["workspace_id"]
            for fixture in ("issues.json", "conversations.json"):
                response = client.post(
                    f"/api/v1/projects/{project}/imports",
                    content=(FIXTURES / fixture).read_bytes(),
                    headers={"Content-Type": "application/json"},
                )
                job = response.json()["id"]
                for _ in range(100):
                    if client.get(f"/api/v1/jobs/{job}").json()["state"] == "succeeded":
                        break
                    time.sleep(0.2)
                else:
                    raise AssertionError("Isolated import timed out")
        result = subprocess.run(
            ["node", "tests/actual-workflow.mjs"],
            cwd=root / "frontend",
            input=json.dumps(
                {
                    "site": f"http://localhost:{site_port}",
                    "api": f"http://localhost:{api_port}",
                    "email": reviewer,
                    "password": PASSWORD,
                    "project": str(project),
                    "workspace": workspace,
                }
            ),
            capture_output=True,
            text=True,
            timeout=100,
        )
        if result.returncode:
            print(result.stderr[-3000:])
            raise AssertionError("Actual frontend verification failed")
        summary = json.loads(result.stdout)
        with Session(engine()) as db:
            job = db.get(Job, UUID(summary["job"]))
            assert job.state == "succeeded"
            runs = db.scalars(select(AgentRun).where(AgentRun.job_id == job.id)).all()
            assert len(runs) == 5 and all(run.status == "succeeded" for run in runs)
            assert db.get(Draft, UUID(summary["draft"])) is not None
        print(
            "PASS: frontend -> API -> PostgreSQL -> private queue -> "
            "Celery -> five stages -> reviewable draft"
        )
        print("Fresh isolated database retained:", name)
        print("Stage states:", summary["stages"])
    finally:
        for process in processes:
            if process.poll() is None:
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                )
                process.wait(timeout=10)
        print("Only isolated test processes stopped; database retained; no paid calls")


if __name__ == "__main__":
    main()
