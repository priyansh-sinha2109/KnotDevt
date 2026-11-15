"use client";

import { useEffect, useState, type FormEvent } from "react";
import {
  ArrowRight,
  Bot,
  Check,
  CircleDashed,
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
  canAssign,
  openDraft,
  jobId,
  setJobId,
}: {
  api: Api;
  projectId: string;
  reviewer: boolean;
  canAssign: boolean;
  openDraft: (id: string) => void;
  jobId: string;
  setJobId: (id: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [recipientRefresh, setRecipientRefresh] = useState(0);
  const [assignment, setAssignment] = useState({ busy: false, error: "" });
  const recipients = useResource<Schema["RecipientOption"][]>(api, `/projects/${projectId}/recipients`, recipientRefresh);

  async function assignRecipient(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (assignment.busy) return;
    const form = event.currentTarget;
    const email = String(new FormData(form).get("email") ?? "").trim();
    setAssignment({ busy: true, error: "" });
    try {
      await api(`/projects/${projectId}/recipients`, { method: "POST", body: { email } });
      setRecipientRefresh((value) => value + 1);
      form.reset();
      setAssignment({ busy: false, error: "" });
    } catch (error) {
      setAssignment({ busy: false, error: message(error) });
    }
  }
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
      } satisfies Schema["AgentInput"];
      const job = await api<Schema["JobView"]>(
        `/projects/${projectId}/agent-jobs`,
        { method: "POST", body },
      );
      setJobId(job.id);
    } catch (error) {
      setError(message(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="flow">
      <section className="panel flow">
        <div className="eyebrow">
          <Bot size={17} /> ORCHESTRATION
        </div>
        <h2>Five-agent workflow</h2>
        {canAssign && (
          <details>
            <summary>Assign an existing workspace member</summary>
            <form className="row" onSubmit={assignRecipient}>
              <label>Member email <input type="email" name="email" required maxLength={254} /></label>
              <button className="button" disabled={assignment.busy}>Add recipient</button>
            </form>
            {assignment.error && <p role="alert" className="error">{assignment.error}</p>}
          </details>
        )}
        <p>
          The Decision Analyst and Work Mapper can run in parallel. A reviewer
          checks the completed draft before publication.
        </p>
        <form className="flow" onSubmit={submit}>
          <label>
            Handover task
            <input
              required
              name="task"
              maxLength={500}
              placeholder="What should the recipient be ready to do?"
            />
          </label>
          <Load data={recipients}>{(options) => options.length ? (
            <fieldset>
              <legend>Who is taking over this project?</legend>
              {options.map(({ id, email }) => (
                <label key={id} className="row"><input type="checkbox" name="audience" value={id} /> {email}</label>
              ))}
            </fieldset>
          ) : <p>No recipients have been assigned to this project.</p>}</Load>
          <button className="button button-blue" disabled={busy || !recipients?.value?.length}>
            {busy ? "Queuing…" : "Run workflow"}
            <ArrowRight size={16} />
          </button>
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
    <section className="panel flow">
      <div className="row spread">
        <h2>Execution stages</h2>
        {data?.job && <Badge value={data.job.phase} />}
      </div>
      {jobId && <small className="mono">Job {jobId}</small>}
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
      {data?.job?.error_code && (
        <p className="error">{label(data.job.error_code)}</p>
      )}
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
              <div className="agent-node">
                {latest?.status === "succeeded" ? (
                  <Check size={17} />
                ) : (
                  <CircleDashed size={17} />
                )}
              </div>
              <div className="flow">
                <div className="row spread">
                  <strong>{name}</strong>
                  <Badge
                    value={
                      latest?.status ?? (data?.job?.phase === "awaiting_provider_authorization" ? "awaiting_provider_authorization" : jobId ? "pending" : "not_started")
                    }
                  />
                </div>
                {(id === "decision_analyst" || id === "work_mapper") && (
                  <small className="stage-track">Parallel analysis</small>
                )}
                <p>{description}</p>
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
          <p>Open the draft to confirm evidence and critical gaps.</p>
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
  if ("evidence" in output)
    return (
      <ul className="outline">
        {output.evidence.map((item) => (
          <li key={item.revision_id}>
            <strong>{item.source_id}</strong> · {item.excerpt}
          </li>
        ))}
      </ul>
    );
  if ("questions" in output)
    return (
      <div className="flow">
        <strong>{output.title}</strong>
        <ol className="outline">
          {output.questions.map((item) => (
            <li key={item.dimension}>{item.prompt}</li>
          ))}
        </ol>
      </div>
    );
  return (
    <div className="flow">
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
    </div>
  );
}
