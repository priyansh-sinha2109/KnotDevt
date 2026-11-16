"use client";

import { useEffect, useState, type FormEvent } from "react";
import {
  ArrowRight,
  Bot,
  Check,
  CircleDashed,
  Clock3,
  GitBranch,
  FileText,
  Play,
  ShieldCheck,
  Sparkles,
  UserRoundCheck,
  XCircle,
} from "lucide-react";
import { ApiError, label, message, type Api, type Schema } from "./api";
import { Badge, Load, useResource } from "./data";

const stages = [
  [
    "context_collector",
    "Context Collector",
    "Gather sources visible to the intended audience.",
  ],
  [
    "decision_analyst",
    "Decision Analyst",
    "Identify decisions and their rationale.",
  ],
  ["work_mapper", "Work Mapper", "Identify unfinished work and dependencies."],
  [
    "evidence_auditor",
    "Evidence Auditor",
    "Validate source spans and surface gaps.",
  ],
  ["readiness_coach", "Readiness Coach", "Propose a version-bound rehearsal."],
];

type StageStatus = "not_started" | "queued" | "running" | "succeeded" | "failed" | "stopped" | "awaiting_review";

function stageStatus(status: string | undefined, phase: string | undefined, hasJob: boolean): StageStatus {
  if (status === "succeeded") return "succeeded";
  if (status === "failed") return "failed";
  if (status === "running") return "running";
  if (phase === "awaiting_provider_authorization") return "stopped";
  if (phase === "awaiting_human_review") return "awaiting_review";
  if (phase === "queued" || phase === "waiting_retry") return "queued";
  return hasJob ? "not_started" : "not_started";
}

const statusCopy: Record<StageStatus, { label: string; tone: string; icon: typeof Check }> = {
  not_started: { label: "Not started", tone: "neutral", icon: CircleDashed },
  queued: { label: "Queued", tone: "warning", icon: Clock3 },
  running: { label: "Running", tone: "active", icon: Play },
  succeeded: { label: "Succeeded", tone: "success", icon: Check },
  failed: { label: "Failed", tone: "danger", icon: XCircle },
  stopped: { label: "Waiting for authorization", tone: "warning", icon: ShieldCheck },
  awaiting_review: { label: "Awaiting review", tone: "active", icon: UserRoundCheck },
};

function StatusBadge({ status }: { status: StageStatus }) {
  const copy = statusCopy[status];
  const Icon = copy.icon;
  return <span className={`workflow-status ${copy.tone}`}><Icon size={13} /> {copy.label}</span>;
}

function nextActionText(job: Schema["JobView"]) {
  if (job.phase === "awaiting_human_review") return "Review the generated handover";
  if (job.state === "failed") return "Inspect the failed stage";
  if (job.phase === "queued") return "Waiting for the worker to begin";
  if (job.phase === "awaiting_provider_authorization") return "Provider authorization required";
  if (job.phase === "waiting_retry") return "Retry scheduled automatically";
  if (job.state === "succeeded") return "Open the review queue";
  return "Workflow is processing";
}

function runEvent(run: Schema["RunView"] | undefined, siblingFailed: boolean) {
  if (!run) return "Ready when the previous stage completes";
  if (run.status === "succeeded") return `Attempt ${run.attempt} · Validated output saved`;
  if (run.error_code === "stage_failed" && siblingFailed) return `Attempt ${run.attempt} · Stopped after parallel stage failure`;
  return `Attempt ${run.attempt} · ${run.error_code ? label(run.error_code) : "Processing stopped"}`;
}

export { Sources } from "./sources-workspace";

type PublicIssue = Schema["GitHubSnapshot"];

export function PublicIssuePreview({ api, sourceId }: { api: Api; sourceId: string }) {
  const [issue, setIssue] = useState<PublicIssue>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function check() {
    setBusy(true);
    setError("");
    try {
      setIssue(await api<PublicIssue>(`/sources/${sourceId}/public-issue`, { method: "POST" }));
    } catch (error) {
      setError(message(error));
    } finally {
      setBusy(false);
    }
  }

  return <section className="panel flow" aria-label="Public GitHub comparison">
    <button className="button" disabled={busy} onClick={check}>{busy ? "Checking GitHub…" : "Check public GitHub issue"}</button>
    {error && <p role="alert" className="error">{error}</p>}
    {issue && <>
      <div className="eyebrow">Retrieved from the official GitHub API</div>
      <h3>{issue.title} · {issue.repository} #{issue.number}</h3>
      <p>{issue.author} · {issue.state} · retrieved {new Date(issue.retrieved_at).toLocaleString()}</p>
      <p>This is a separate live snapshot. Existing citations still refer to the imported text.</p>
      <a href={issue.original_url} target="_blank" rel="noopener noreferrer">Open GitHub issue</a>
      <details><summary>Snapshot details</summary>
        <p>Created {new Date(issue.created_at).toLocaleString()} · updated {new Date(issue.updated_at).toLocaleString()}</p>
        <p>Assigned at snapshot: {issue.assignees.length ? issue.assignees.join(", ") : "No one listed"}</p>
        {issue.closed_at && <p>Closed {new Date(issue.closed_at).toLocaleString()} · closing state alone does not verify a fix.</p>}
        <p>Snapshot fingerprint <code>{issue.snapshot_sha256}</code></p>
      </details>
      <details><summary>Read exact issue body</summary><pre className="source-text">{issue.body}</pre></details>
    </>}
  </section>;
}

function useJob(api: Api, id: string, showRuns = false) {
  const [result, setResult] = useState<{
    job?: Schema["JobView"];
    runs?: Schema["RunView"][];
    error?: string;
  }>();
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!id) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let failures = 0;
    let request: AbortController | undefined;
    const poll = async () => {
      request = new AbortController();
      const deadline = setTimeout(() => request?.abort(), 15000);
      try {
        const job = await api<Schema["JobView"]>(`/jobs/${id}`, {
          signal: request.signal,
        });
        // Read stages after job state so a terminal poll sees all committed attempts.
        const runs = showRuns
          ? await api<Schema["RunView"][]>(`/jobs/${id}/runs`, {
              signal: request.signal,
            })
          : undefined;
        if (controller.signal.aborted) return;
        failures = 0;
        setResult({ job, runs });
        if ((job.state === "queued" && job.phase !== "awaiting_provider_authorization") || job.phase === "reconciling")
          timer = setTimeout(poll, 2000);
      } catch (error) {
        if (controller.signal.aborted) return;
        failures += 1;
        const transient = !(error instanceof ApiError) || [408, 429, 500, 502, 503, 504].includes(error.status);
        const retrying = transient && failures <= 5;
        setResult((previous) => ({ ...previous, error: retrying
          ? "Status check interrupted. Retrying automatically..."
          : message(error) }));
        if (retrying) timer = setTimeout(poll, Math.min(30000, 1000 * 2 ** failures) * (0.8 + Math.random() * 0.4));
      } finally {
        clearTimeout(deadline);
      }
    };
    void poll();
    return () => {
      controller.abort();
      request?.abort();
      clearTimeout(timer);
    };
  }, [api, id, showRuns, retry]);
  return { ...result, retry: () => setRetry((value) => value + 1) };
}

export function ImportStatus({
  api,
  id,
  refresh,
}: {
  api: Api;
  id: string;
  refresh: () => void;
}) {
  const result = useJob(api, id);
  const [retryError, setRetryError] = useState("");
  const [retrying, setRetrying] = useState(false);
  async function retryImport() {
    if (retrying) return;
    setRetrying(true);
    setRetryError("");
    try {
      await api(`/jobs/${id}/retry`, { method: "POST" });
      result.retry();
    } catch (error) { setRetryError(message(error)); }
    finally { setRetrying(false); }
  }
  const complete = result?.job?.state === "succeeded";
  useEffect(() => {
    if (complete) refresh();
  }, [complete, refresh]);
  if (result?.error)
    return (
      <p role="alert" className="error">
        {result.error}
        <button className="button button-quiet" onClick={result.retry}>Retry status check</button>
      </p>
    );
  return (
    <div className="row" role="status">
      <Badge value={result?.job?.phase ?? "pending"} />
      {result?.job?.phase === "waiting_retry" && (
        <span>A temporary interruption occurred. Retrying automatically.</span>
      )}
      {result?.job?.error_code && <span>{label(result.job.error_code)}</span>}
      {result?.job?.state === "failed" && (result.job.error_code === "processing_failed"
        ? <button className="button button-quiet" disabled={retrying} onClick={retryImport}>Retry import</button>
        : <span>Correct the source input or permissions before submitting again.</span>)}
      {retryError && <span role="alert">{retryError}</span>}
      {result?.job?.state === "succeeded" && (
        <>
          <span>{result.job.revisions?.length ?? 0} reported revisions</span>
          <button className="button button-quiet" onClick={refresh}>
            Refresh source library
          </button>
        </>
      )}
    </div>
  );
}

export function AgentWorkflow({
  api,
  projectId,
  reviewer,
  openDraft,
  jobId,
  setJobId,
}: {
  api: Api;
  projectId: string;
  reviewer: boolean;
  openDraft: (id: string) => void;
  jobId: string;
  setJobId: (id: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [mode, setMode] = useState<"source_based" | "ai_assisted">("source_based");
  const recipients = useResource<Schema["RecipientOption"][]>(api, `/projects/${projectId}/recipients`);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const audience = fields.getAll("audience").map(String).filter(Boolean);
    if (!audience.length || audience.length > 8) {
      setError("Select between one and eight recipients.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const body = {
        task: String(fields.get("task")).trim(),
        audience: [...new Set(audience)],
      };
      if (mode === "source_based") {
        const draft = await api<Schema["DraftView"]>(
          `/projects/${projectId}/source-handover-drafts`,
          { method: "POST", body },
        );
        openDraft(draft.id);
      } else {
        const job = await api<Schema["JobView"]>(
          `/projects/${projectId}/agent-jobs`,
          { method: "POST", body: body satisfies Schema["AgentInput"] },
        );
        setJobId(job.id);
      }
    } catch (error) {
      setError(message(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="flow">
      <section className="workflow-hero panel">
        <div className="eyebrow"><Sparkles size={16} /> AI WORKFLOW</div>
        <h1>Turn project evidence into a confident handover.</h1>
        <p className="workflow-lead">KnotDevt analyzes selected project evidence through five AI-assisted stages before a human review.</p>
        <div className="workflow-pipeline" aria-label="Five workflow stages">
          {stages.map(([id, name], index) => <div className="pipeline-step" key={id}><span>{index + 1}</span><strong>{name}</strong>{index < stages.length - 1 && <ArrowRight size={14} />}</div>)}
        </div>
        <div className="workflow-notes"><span><GitBranch size={15} /> Decision Analyst + Work Mapper run in parallel</span><span><UserRoundCheck size={15} /> Human review is required before publication</span></div>
      </section>
      <section className="handover-modes" aria-label="Choose handover mode">
        <button type="button" className={`handover-mode ${mode === "source_based" ? "selected" : ""}`} onClick={() => setMode("source_based")}>
          <span className="mode-icon"><FileText size={21} /></span><span><strong>Source-Based Handover</strong><small>Create a structured handover using your project&apos;s real evidence.</small><em>Zero AI tokens · Evidence-linked · Human reviewed</em></span>
        </button>
        <button type="button" className={`handover-mode ${mode === "ai_assisted" ? "selected" : ""}`} onClick={() => setMode("ai_assisted")}>
          <span className="mode-icon"><Sparkles size={21} /></span><span><strong>AI-Assisted Handover</strong><small>Use five specialized agents to prepare an evidence-backed handover.</small><em>Five-agent analysis · Evidence verification · Human review</em></span>
        </button>
      </section>
      <section className="panel workflow-setup">
        <div className="section-heading"><div><div className="eyebrow">{mode === "source_based" ? <><FileText size={16} /> SOURCE-BASED</> : <><Bot size={16} /> AI-ASSISTED</>}</div><h2>{mode === "source_based" ? "Create source-based handover" : "Create AI handover"}</h2></div><span className="step-count">1 · 2 · 3</span></div>
        <p className="muted">{mode === "source_based" ? "KnotDevt will preserve authorized project evidence exactly as recorded. Reviewers confirm every conclusion before publication." : "Enter the outcome you want the recipient to be ready for, then confirm who can access the imported evidence."}</p>
        <form className="flow" onSubmit={submit}>
          <div className="context-strip"><span><strong>Project context</strong><small>Permission-aware evidence</small></span><span><ShieldCheck size={15} /> Authorized sources are selected by the backend</span></div>
          <label>
            What should the AI prepare?
            <input
              required
              name="task"
              maxLength={500}
              placeholder="e.g. Prepare a handover covering pending work, key decisions, blockers and next steps."
            />
          </label>
          <div className="suggestions" aria-label="Suggested tasks">{["Summarize pending work and next steps", "Explain key decisions and blockers", "Prepare an onboarding handover"].map((suggestion) => <button type="button" className="suggestion" key={suggestion} onClick={(event) => { const input = event.currentTarget.closest("form")?.querySelector<HTMLInputElement>('input[name="task"]'); if (input) { input.value = suggestion; input.focus(); } }}>{suggestion}</button>)}</div>
          <Load data={recipients}>{(options) => options.length ? (
            <label>Authorized recipient<select name="audience" defaultValue=""><option value="" disabled>Select a project recipient</option>{options.map(({ id, email }) => <option key={id} value={id}>{email}</option>)}</select><small className="muted">Only evidence this recipient is authorized to access will be included.</small></label>
          ) : <p>No recipients have been assigned to this project.</p>}</Load>
          <button className="button button-blue workflow-cta" disabled={busy || !recipients?.value?.length}>
            {busy ? "Preparing handover…" : mode === "source_based" ? "Create Source-Based Handover" : "Create AI Handover"}
            <ArrowRight size={16} />
          </button><small className="muted">You can inspect every citation and stage result before anything is published.</small>
        </form>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
      </section>
      <AgentStages
        key={jobId}
        {...{ api, projectId, jobId, reviewer, openDraft }}
      />
    </div>
  );
}

function AgentStages({
  api,
  projectId,
  jobId,
  reviewer,
  openDraft,
}: {
  api: Api;
  projectId: string;
  jobId: string;
  reviewer: boolean;
  openDraft: (id: string) => void;
}) {
  const data = useJob(api, jobId, true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (!jobId) return <section className="panel workflow-empty"><div className="empty-icon"><Sparkles size={22} /></div><div><div className="eyebrow">READY WHEN YOU ARE</div><h2>Your next handover starts here</h2><p>1. Enter a handover task&nbsp;&nbsp; 2. Confirm recipients and evidence scope&nbsp;&nbsp; 3. Run the workflow.</p></div></section>;
  async function makeDraft() {
    setBusy(true);
    setError("");
    try {
      const body = { agent_job_id: jobId } satisfies Schema["DraftInput"];
      const draft = await api<Schema["DraftView"]>(
        `/projects/${projectId}/drafts`,
        { method: "POST", body },
      );
      openDraft(draft.id);
    } catch (error) {
      setError(message(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel flow execution-panel">
      <div className="section-heading"><div><div className="eyebrow"><Play size={15} /> LIVE RUN</div><h2>Execution stages</h2></div>{data?.job && <StatusBadge status={stageStatus(undefined, data.job.phase, true)} />}</div>
      {jobId && <div className="job-summary"><span><strong>Latest run</strong><code>{jobId}</code></span>{data?.job && <><span><strong>Created</strong>{new Date(data.job.created_at).toLocaleString()}</span><span><strong>Progress</strong>{data.runs?.filter((run) => run.status === "succeeded").length ?? 0} of 5 stages complete</span><span><strong>Next action</strong>{nextActionText(data.job)}</span></>}</div>}
      {(error || data?.error) && (
        <p className="error" role="alert">
          {error || data?.error}
          {data?.error && <button className="button button-quiet" onClick={data.retry}>Retry status check</button>}
        </p>
      )}
      {error && reviewer && (
        <button className="button button-quiet" onClick={() => openDraft("")}>
          Open review queue
        </button>
      )}
      {data?.job?.error_code && <div className="workflow-error"><strong>{data.runs?.some((run) => run.error_code === "provider_invalid_request") ? "The AI provider rejected the Decision Analyst request." : data.job.state === "failed" ? "This workflow stopped before completion." : label(data.job.error_code)}</strong><span>{data.runs?.some((run) => run.error_code === "provider_invalid_request") ? "Work Mapper was stopped with the parallel analysis after that provider error; later stages did not run." : `${label(data.job.error_code)}. Later stages could not continue.`}</span><details><summary>View technical details</summary><code>{data.runs?.find((run) => run.error_code)?.error_code ?? data.job.error_code}</code></details></div>}
      {data?.job?.phase === "waiting_retry" && (
        <p className="notice" role="status">
          The AI provider was temporarily unavailable. Your completed stages are
          safe, and KnotDevt will resume automatically.
        </p>
      )}
      {data?.job?.phase === "reconciling" && <p role="status">Published. Finalizing the workflow checkpoint; recovery will retry automatically.</p>}
      {data?.job?.phase === "awaiting_provider_authorization" && <p className="notice" role="status">Awaiting AI provider authorization. Your job is saved. Execution requires confirmation of credential rotation and a spending limit.</p>}
      {data?.job?.phase === "reconciliation_failed" && <p role="alert">Published handover preserved. Checkpoint recovery needs operator attention.</p>}
      <ol className="agent-list">
        {stages.map(([id, name, description], index) => {
          const attempts = data?.runs?.filter((run) => run.role === id) ?? [];
          const latest = attempts.at(-1);
          return (
            <li
              key={id}
              className="enter"
              style={{ animationDelay: `${index * 45}ms` }}
            >
              <div className={`agent-node node-${stageStatus(latest?.status, data?.job?.phase, Boolean(jobId))}`}><StatusBadge status={stageStatus(latest?.status, data?.job?.phase, Boolean(jobId))} /></div>
              <div className="flow">
                <div className="row spread">
                  <strong>{name}</strong>
                </div>
                {(id === "decision_analyst" || id === "work_mapper") && (
                  <small className="stage-track">Parallel analysis</small>
                )}
                <p>{description}</p><small className="stage-event">{runEvent(latest, attempts.some((run) => run.error_code === "provider_invalid_request"))}</small>
                {attempts.map((run) => (
                  <details key={run.id}>
                    <summary>
                      Attempt {run.attempt} · {label(run.status)}
                    </summary>
                    {run.error_code && <p>{label(run.error_code)}</p>}
                    {run.output && <StageOutput output={run.output} />}
                  </details>
                ))}
              </div>
            </li>
          );
        })}
      </ol>
      {data?.job?.phase === "awaiting_human_review" && (
        <div className="notice flow">
          <strong>Human review checkpoint</strong>
          <p>All stages are complete. Review evidence and critical gaps before publication.</p>
          {reviewer && (
            <button
              className="button button-blue"
              disabled={busy}
              onClick={makeDraft}
            >
              {busy ? "Opening…" : "Open review draft"}
            </button>
          )}
        </div>
      )}
    </section>
  );
}

function StageOutput({
  output,
}: {
  output: NonNullable<Schema["RunView"]["output"]>;
}) {
  const raw = JSON.stringify(output, null, 2);
  const copy = () => { void navigator.clipboard?.writeText(raw); };
  const summary = "evidence" in output
    ? `${output.evidence.length} source revision${output.evidence.length === 1 ? "" : "s"} collected`
    : "questions" in output
      ? `${output.questions.length} readiness question${output.questions.length === 1 ? "" : "s"} prepared`
      : `${output.claims.length} finding${output.claims.length === 1 ? "" : "s"} produced`;
  if ("evidence" in output)
    return (
      <div className="stage-output"><strong>{summary}</strong><ul className="outline">
        {output.evidence.map((item) => (
          <li key={item.revision_id}>
            <strong>{item.source_id}</strong> · {item.excerpt}
          </li>
        ))}
      </ul><RawOutput raw={raw} copy={copy} /></div>
    );
  if ("questions" in output)
    return (
      <div className="stage-output flow">
        <strong>{summary}</strong>
        <strong>{output.title}</strong>
        <ol className="outline">
          {output.questions.map((item) => (
            <li key={item.dimension}>{item.prompt}</li>
          ))}
        </ol>
        <RawOutput raw={raw} copy={copy} /></div>
    );
  return (
    <div className="stage-output flow">
      <strong>{summary}</strong>
      {output.claims.map((item) => {
        const claim = "content" in item ? item.content : item;
        return (
          <div className="citation" key={item.key}>
            <div className="row">
              <Badge value={claim.kind} />
              <Badge value={claim.status} />
            </div>
            <p>{claim.statement}</p>
            {"flags" in item && (
              <div className="row">
                {item.flags.map((flag) => (
                  <Badge key={flag} value={flag} />
                ))}
              </div>
            )}
          </div>
        );
      })}
      {"unresolved" in output &&
        output.unresolved.map((item) => (
          <p className="notice" key={item}>
            {item}
          </p>
        ))}
      {"missing_rationale" in output &&
        output.missing_rationale.map((item) => (
          <p className="notice" key={item}>
            {item}
          </p>
        ))}
      {"recurring_problem_candidates" in output &&
        output.recurring_problem_candidates.map((item) => (
          <p className="notice" key={item}>
            {item}
          </p>
        ))}
      <RawOutput raw={raw} copy={copy} />
    </div>
  );
}

function RawOutput({ raw, copy }: { raw: string; copy: () => void }) {
  return <details className="raw-output"><summary>View raw JSON</summary><button type="button" className="button button-quiet" onClick={copy}>Copy JSON</button><pre>{raw}</pre></details>;
}
