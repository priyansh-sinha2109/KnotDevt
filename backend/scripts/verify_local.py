"""Exercise the five synthetic judge scenes over the local HTTP API."""

import argparse
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx

from scripts.seed_demo import demo_password

BASE_URL = "http://127.0.0.1:8080"
FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
ROLES = {
    "context_collector",
    "decision_analyst",
    "work_mapper",
    "evidence_auditor",
    "readiness_coach",
}


def request(
    client: httpx.Client, method: str, path: str, status: int, **kwargs: Any
) -> Any:
    response = client.request(method, path, **kwargs)
    if response.status_code != status:
        raise RuntimeError(
            f"{method} {path} returned {response.status_code}, expected {status}"
        )
    return response.json() if response.content else None


def wait_job(
    client: httpx.Client, job_id: str, tick: Callable[[], None] | None
) -> dict[str, Any]:
    if tick is not None:
        tick()
    until = time.monotonic() + 60
    while time.monotonic() < until:
        job = request(client, "GET", f"/api/v1/jobs/{job_id}", 200)
        if job["state"] == "succeeded":
            return job
        if job["state"] == "failed":
            raise RuntimeError(f"Job {job_id} failed with {job['error_code']}")
        time.sleep(0.2)
    raise RuntimeError(
        f"Job {job_id} did not complete. Check Celery worker and scheduler."
    )


def run_workflow(
    lead: httpx.Client,
    recipient: httpx.Client,
    restricted: httpx.Client,
    project_id: UUID,
    recipient_id: UUID,
    *,
    tick: Callable[[], None] | None = None,
) -> dict[str, Any]:
    project = f"/api/v1/projects/{project_id}"
    jobs = [
        request(
            lead,
            "POST",
            project + "/imports",
            202,
            content=(FIXTURES / name).read_bytes(),
            headers={
                "Content-Type": "application/json",
                "Idempotency-Key": f"demo-{name}",
            },
        )["id"]
        for name in ("issues.json", "conversations.json")
    ]
    reports = [wait_job(lead, job_id, tick) for job_id in jobs]
    assert [len(report["revisions"]) for report in reports] == [2, 2]
    print("1. Reviewer imported two synthetic source files.")

    job = request(
        lead,
        "POST",
        project + "/agent-jobs",
        202,
        json={
            "task": "Prepare the event-registration payment release",
            "audience": [str(recipient_id)],
            "source_ids": ["PAY-21", "M-07", "C-19"],
        },
    )
    wait_job(lead, job["id"], tick)
    runs = request(lead, "GET", f"/api/v1/jobs/{job['id']}/runs", 200)
    assert {row["role"] for row in runs if row["status"] == "succeeded"} == ROLES
    assert all(row["output"] is not None for row in runs)
    assert "FINANCE-ONLY" not in str(runs)
    print("2. Five agent outputs are ready for review.")
    for row in sorted(runs, key=lambda item: item["role"]):
        print(f"   {row['role']} · {row['model']} · {row['status']}")

    assert request(recipient, "GET", project + "/versions", 200)["items"] == []
    draft = request(
        lead, "POST", project + "/drafts", 201, json={"agent_job_id": job["id"]}
    )
    by_status = {row["claim"]["status"]: row["claim"] for row in draft["claims"]}
    assert {"proposed", "accepted", "implemented", "unresolved"} <= by_status.keys()
    monday_id = by_status["accepted"]["id"]
    trace_url = f"/api/v1/claims/{monday_id}/trace"
    current_trace = request(lead, "GET", trace_url, 200)
    assert current_trace["selected"]["evidence"][0]["original_id"] == "M-07"
    assert "rollback ownership" in " ".join(current_trace["outline"]).lower()
    print("3. Context Trace shows Monday approval and unresolved rollback ownership.")

    blocker = next(
        row["claim"] for row in draft["claims"] if row["claim"]["kind"] == "blocker"
    )
    blocker_trace = request(lead, "GET", f"/api/v1/claims/{blocker['id']}/trace", 200)
    source = blocker_trace["selected"]["evidence"][0]
    evidence = {
        "revision_id": source["revision_id"],
        "start": source["start"],
        "end": source["end"],
        "quote": source["excerpt"],
        "relation": source["relation"],
    }
    edited = request(
        lead,
        "PATCH",
        f"/api/v1/claims/{blocker['id']}",
        200,
        json={
            "draft_id": draft["id"],
            "expected_revision": draft["revision"],
            "reason": "Clarify escalation while preserving the unresolved blocker.",
            "content": {
                "kind": "blocker",
                "status": "unresolved",
                "evidence": [evidence],
                "statement": "Rollback ownership is unresolved. Escalate to lead.",
            },
        },
    )
    rubric = draft["proposed_rubric"]
    approved = request(
        lead,
        "POST",
        f"/api/v1/drafts/{draft['id']}/approve",
        201,
        json={
            "expected_revision": edited["draft_revision"],
            "rubric": rubric,
        },
    )
    version_id = approved["id"]
    version = f"/api/v1/versions/{version_id}"
    trace = request(recipient, "GET", trace_url, 200, params={"version_id": version_id})
    decisions = {
        row["evidence"][0]["original_id"]: row["claim"]["status"]
        for row in trace["timeline"]
        if row["claim"]["kind"] == "decision"
    }
    assert decisions == {
        "PAY-21": "proposed",
        "C-19": "implemented",
        "M-07": "accepted",
    }
    assert "reason for choosing Monday is missing" in " ".join(trace["unresolved"])
    receipt = request(recipient, "POST", version + "/receipt", 201)
    assert request(recipient, "POST", version + "/receipt", 200) == receipt
    print("4. Reviewer approved the corrected version. Recipient acknowledged receipt.")

    rubric_id = approved["handover"]["rubric_id"]
    rubric_url = f"/api/v1/rubrics/{rubric_id}"
    questions = request(recipient, "GET", rubric_url, 200)
    assert "correct_choice" not in str(questions)
    attempt = request(
        recipient,
        "POST",
        rubric_url + "/attempts",
        201,
        json={
            "client_attempt_id": str(uuid4()),
            "answers": {
                q["dimension"]: q["correct_choice"] for q in rubric["questions"]
            },
            "explanation": "Wait for testing and escalate the missing rollback owner.",
        },
    )
    assert attempt["score"] == 100 and attempt["status"] == "blocked_by_project_gap"
    sources = request(
        lead, "GET", project + "/sources", 200, params={"query": "FIN-12"}
    )
    private_id = next(
        row["id"] for row in sources["items"] if row["original_id"] == "FIN-12"
    )
    for path in (
        version,
        rubric_url,
        f"/api/v1/sources/{private_id}",
        project + "/sources",
    ):
        denied = request(restricted, "GET", path, 404)
        assert "FINANCE-ONLY" not in str(denied)
    print("5. Readiness stayed blocked at 100/100. Restricted requests were denied.")
    return {
        "version_id": version_id,
        "agent_job_id": job["id"],
        "attempt_id": attempt["id"],
    }


def login(client: httpx.Client, email: str, password: str) -> UUID:
    identity = request(
        client,
        "POST",
        "/api/v1/auth/login",
        200,
        json={"email": email, "password": password},
    )
    client.headers["X-CSRF-Token"] = identity["csrf_token"]
    return UUID(identity["user_id"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=UUID, required=True)
    args = parser.parse_args()
    password = demo_password()
    with (
        httpx.Client(base_url=BASE_URL, timeout=6) as lead,
        httpx.Client(base_url=BASE_URL, timeout=6) as recipient,
        httpx.Client(base_url=BASE_URL, timeout=6) as restricted,
    ):
        request(lead, "GET", "/health/ready", 200)
        login(lead, "reviewer@knotdevt.test", password)
        recipient_id = login(recipient, "recipient@knotdevt.test", password)
        login(restricted, "restricted@knotdevt.test", password)
        report = run_workflow(lead, recipient, restricted, args.project, recipient_id)
        print(f"Verified handover {report['version_id']}")


if __name__ == "__main__":
    main()
