from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypedDict
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import auditor, fake, provider
from app.agents.instructions import VERSION
from app.db.evidence import AgentRun
from app.db.session import engine
from app.schemas.agents import (
    AuditOutput,
    CoachInput,
    ContextBundle,
    DecisionOutput,
    RubricProposal,
    Stage,
    WorkOutput,
)
from app.services.imports import JobFailure


class State(TypedDict, total=False):
    started: bool
    context: dict[str, Any]
    decisions: dict[str, Any]
    work: dict[str, Any]
    audit: dict[str, Any]
    rubric: dict[str, Any]
    approved: bool


@dataclass(frozen=True)
class RunConfig:
    job_id: UUID
    provider: str
    model: str
    attempts: int
    timeout: int
    token_limit: int


def run_stage[Output: BaseModel](
    cfg: RunConfig,
    stage: Stage,
    schema: type[Output],
    compute: Callable[[], Output],
    model: str,
) -> dict[str, Any]:
    for attempt in range(1, cfg.attempts + 1):
        with Session(engine()) as db, db.begin():
            record = db.scalar(
                select(AgentRun).where(
                    AgentRun.job_id == cfg.job_id,
                    AgentRun.role == stage,
                    AgentRun.attempt == attempt,
                )
            )
            if record is not None and record.status == "succeeded":
                return schema.model_validate(record.output).model_dump(mode="json")
            if record is not None and record.status == "failed":
                continue
            if record is None:
                record = AgentRun(
                    job_id=cfg.job_id,
                    role=stage,
                    model=model,
                    prompt_version=VERSION,
                    attempt=attempt,
                    status="running",
                    timeout_seconds=cfg.timeout,
                    attempt_limit=cfg.attempts,
                )
                db.add(record)
                db.flush()
            run_id = record.id

        try:
            value = compute().model_dump(mode="json")
        except Exception as exc:
            with Session(engine()) as db, db.begin():
                record = db.get(AgentRun, run_id)
                assert record is not None
                record.status = "failed"
                record.error_code = (
                    "invalid_output" if isinstance(exc, ValueError) else "stage_failed"
                )
            continue

        with Session(engine()) as db, db.begin():
            record = db.get(AgentRun, run_id)
            assert record is not None
            record.status = "succeeded"
            record.output = value
        return value
    raise JobFailure("agent_stage_failed")


def run_graph(
    cfg: RunConfig,
    bundle: ContextBundle,
    saver: PostgresSaver,
    *,
    approval: bool | None = None,
) -> None:
    model = cfg.model if cfg.provider == "gemini" else "deterministic-fixture"

    def context(state: State) -> State:
        return {
            "context": run_stage(
                cfg, "context_collector", ContextBundle, lambda: bundle, "local"
            )
        }

    def decisions(state: State) -> State:
        data = ContextBundle.model_validate(state["context"])
        return {
            "decisions": run_stage(
                cfg,
                "decision_analyst",
                DecisionOutput,
                lambda: (
                    provider.generate(
                        "decision_analyst",
                        data,
                        DecisionOutput,
                        cfg.model,
                        cfg.timeout,
                        cfg.token_limit,
                    )
                    if cfg.provider == "gemini"
                    else fake.decisions(data)
                ),
                model,
            )
        }

    def work(state: State) -> State:
        data = ContextBundle.model_validate(state["context"])
        return {
            "work": run_stage(
                cfg,
                "work_mapper",
                WorkOutput,
                lambda: (
                    provider.generate(
                        "work_mapper",
                        data,
                        WorkOutput,
                        cfg.model,
                        cfg.timeout,
                        cfg.token_limit,
                    )
                    if cfg.provider == "gemini"
                    else fake.work(data)
                ),
                model,
            )
        }

    def evidence_auditor(state: State) -> State:
        return {
            "audit": run_stage(
                cfg,
                "evidence_auditor",
                AuditOutput,
                lambda: auditor.audit(
                    ContextBundle.model_validate(state["context"]),
                    DecisionOutput.model_validate(state["decisions"]),
                    WorkOutput.model_validate(state["work"]),
                ),
                "local",
            )
        }

    def readiness_coach(state: State) -> State:
        data = ContextBundle.model_validate(state["context"])
        audit = AuditOutput.model_validate(state["audit"])

        def prepare() -> RubricProposal:
            if cfg.provider == "gemini":
                result = provider.generate(
                    "readiness_coach",
                    CoachInput(context=data, audit=audit),
                    RubricProposal,
                    cfg.model,
                    cfg.timeout,
                    cfg.token_limit,
                )
            else:
                result = fake.rehearsal(data, audit)
            revision_ids = {item.revision_id for item in data.evidence}
            if any(
                set(item.evidence_revision_ids) - revision_ids
                for item in result.questions
            ):
                raise ValueError("Rubric references unknown evidence")
            return result

        return {
            "rubric": run_stage(cfg, "readiness_coach", RubricProposal, prepare, model)
        }

    def human(state: State) -> State:
        verdict = interrupt({"status": "awaiting_human_review"})
        if not isinstance(verdict, bool):
            raise ValueError("Expected authorized review verdict")
        return {"approved": verdict}

    workflow = StateGraph(State)
    workflow.add_node("collect", context)
    workflow.add_node("decisions", decisions)
    workflow.add_node("work", work)
    workflow.add_node("audit", evidence_auditor)
    workflow.add_node("coach", readiness_coach)
    workflow.add_node("review", human)
    workflow.add_edge(START, "collect")
    workflow.add_edge("collect", "decisions")
    workflow.add_edge("collect", "work")
    workflow.add_edge(["decisions", "work"], "audit")
    workflow.add_edge("audit", "coach")
    workflow.add_edge("coach", "review")
    workflow.add_edge("review", END)
    graph = workflow.compile(checkpointer=saver)
    config: RunnableConfig = {
        "configurable": {"thread_id": str(cfg.job_id)},
        "max_concurrency": 2,
    }
    saved = graph.get_state(config)
    if approval is not None:
        if saved.interrupts:
            graph.invoke(Command(resume=approval), config)
        elif saved.values.get("approved") is not approval:
            raise JobFailure("review_checkpoint_unavailable")
    elif not saved.interrupts and not saved.values.get("approved"):
        graph.invoke(None if saved.values else {"started": True}, config)
        if not graph.get_state(config).interrupts:
            raise JobFailure("review_checkpoint_unavailable")
