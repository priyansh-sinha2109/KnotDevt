"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import {
  ArrowRight,
  Bot,
  Check,
  CircleDashed,
  FilePlus2,
  ScanSearch,
} from "lucide-react";
import { evidenceTitle, label, message, type Api, type Schema } from "./api";
import { Badge, Empty, Load, Pager, useResource } from "./data";

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

async function readSourceExport(file: File) {
  if (!file.size || file.size > 1048576)
    throw new Error("Choose a source file between 1 byte and 1 MiB.");
  let batch;
  try {
    batch = JSON.parse(await file.text());
  } catch {
    throw new Error("This export could not be read.");
  }
  const records = batch?.kind === "issue-events" ? batch.events
    : batch?.kind === "conversation-notes" ? batch.notes : null;
  if (typeof batch?.provider !== "string" || !Array.isArray(records) || !records.length || records.length > 100)
    throw new Error("Choose a supported export with between 1 and 100 records.");
  const preview = records.slice(0, 3).map((record) => {
    if (!record || typeof record.author !== "string" || typeof record.text !== "string")
      throw new Error("Each record needs an author and text.");
    return `${record.author.slice(0, 60)}: ${record.text.slice(0, 100)}`;
  });
  return { batch, count: records.length, preview };
}

export function Sources({
  api,
  projectId,
  editor,
}: {
  api: Api;
  projectId: string;
  editor: boolean;
}) {
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState("");
  const [job, setJob] = useState("");
  const [refresh, setRefresh] = useState(0);
  const refreshSources = useCallback(() => setRefresh((value) => value + 1), []);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [importMode, setImportMode] = useState("task");
  const [filePreview, setFilePreview] = useState<{ text: string; samples?: string[] }>();
  const retry = useRef({ text: "", key: "" });
  const search = query ? `&query=${encodeURIComponent(query)}` : "";
  const data = useResource<Schema["SourcesPage"]>(
    api,
    `/projects/${projectId}/sources?limit=25&offset=${offset}${search}`,
    refresh,
  );
  const source = useResource<Schema["SourceView"]>(
    api,
    selected ? `/sources/${selected}` : "",
  );

  async function importBatch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    setError("");
    setBusy(true);
    try {
      const file = fields.get("batch");
      if (importMode === "file" && !(file instanceof File))
        throw new Error("Choose a source file.");
      const entry = {
        source_id: retry.current.key || crypto.randomUUID(),
        author: String(fields.get("author") ?? "").trim(),
        text: String(fields.get("text") ?? "").trim(),
        reference: String(fields.get("reference") ?? "").trim(),
        event_at: importMode === "file" ? "" : new Date(String(fields.get("date"))).toISOString(),
        event_type: importMode,
      };
      const body = importMode === "file" && file instanceof File
        ? (await readSourceExport(file)).batch
        : importMode === "task"
          ? { kind: "issue-events", provider: "manual", events: [entry] }
          : { kind: "conversation-notes", provider: "manual", notes: [entry] };
      if (new TextEncoder().encode(JSON.stringify(body)).length > 1048576)
        throw new Error("Import exceeds the 1 MiB limit.");
      const fingerprint = JSON.stringify(body, (key, value) => importMode !== "file" && key === "source_id" ? undefined : value);
      if (retry.current.text !== fingerprint)
        retry.current = { text: fingerprint, key: crypto.randomUUID() };
      if (importMode !== "file") entry.source_id = retry.current.key;
      const queued = await api<Schema["JobView"]>(
        `/projects/${projectId}/imports`,
        { method: "POST", body, key: retry.current.key },
      );
      setJob(queued.id);
      retry.current = { text: "", key: "" };
      setFilePreview(undefined);
      form.reset();
    } catch (error) {
      setError(message(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flow">
      <section className="panel flow">
        <h2>Source library</h2>
        <form
          className="row"
          onSubmit={(event) => {
            event.preventDefault();
            setOffset(0);
            setQuery(
              String(
                new FormData(event.currentTarget).get("query") ?? "",
              ).trim(),
            );
          }}
        >
          <input
            name="query"
            aria-label="Search permitted sources"
            placeholder="Search by reference or text"
          />
          <button className="button button-quiet">
            <ScanSearch size={16} /> Search
          </button>
        </form>
        <Load data={data}>
          {(value) => (
            <>
              {!value.items.length && (
                <Empty>No matching sources are visible to your account.</Empty>
              )}
              {value.items.map((item) => (
                <button
                  key={item.id}
                  className="list-item"
                  aria-pressed={item.id === selected}
                  onClick={() => setSelected(item.id)}
                >
                  <span>
                    <strong>{evidenceTitle(item.original_id, item.excerpt)}</strong>
                    <small>
                      {item.author} · {label(item.event_type)}
                    </small>
                  </span>
                  <ArrowRight size={16} />
                </button>
              ))}
              <Pager
                offset={offset}
                next={value.next_offset}
                onChange={setOffset}
              />
            </>
          )}
        </Load>
      </section>
      {selected && (
        <section className="panel flow">
          <Load data={source}>
            {(value) => (
              <>
                <h2>{evidenceTitle(value.original_id, value.excerpt)}</h2>
                <div className="row">
                  <Badge value={value.policy} />
                  <Badge value={value.kind} />
                </div>
                <p className="source-text">{value.excerpt}</p>
                <small>{value.provider === "manual" ? "Manually provided summary" : "Provided source snapshot"} · Original source not independently checked</small>
                <small>{value.reference}</small>
                {editor && /^https:\/\/github\.com\/[^/]+\/[^/]+\/issues\/\d+$/.test(value.reference) && (
                  <PublicIssuePreview key={value.revision_id} api={api} sourceId={value.id} />
                )}
              </>
            )}
          </Load>
        </section>
      )}
      {editor && (
        <section className="panel flow">
          <h2>
            <FilePlus2 size={19} /> Import evidence
          </h2>
          <form className="flow" onSubmit={importBatch}>
            <label>
              What would you like to add?
              <select value={importMode} onChange={(event) => { setImportMode(event.target.value); setFilePreview(undefined); }}>
                <option value="task">Issue or pending task</option>
                <option value="meeting">Meeting notes</option>
                <option value="message">Team conversation</option>
                <option value="file">Upload a supported source export</option>
              </select>
            </label>
            {importMode === "file" ? (
              <><label>Source export <input name="batch" type="file" accept=".json,application/json" required onChange={async (event) => {
                const input = event.currentTarget;
                const file = event.target.files?.[0];
                setFilePreview(undefined);
                if (!file) return;
                try {
                  const { count, preview } = await readSourceExport(file);
                  if (input.isConnected && input.files?.[0] === file)
                    setFilePreview({ text: `${count} records in ${file.name}`, samples: preview });
                } catch (error) {
                  if (input.isConnected && input.files?.[0] === file) setFilePreview({ text: message(error) });
                }
              }} /></label>{filePreview && <div role="status">
                <small>{filePreview.text}</small>
                {!!filePreview.samples?.length && <ul>{filePreview.samples.map((sample, index) => <li key={index}>{sample}</li>)}</ul>}
              </div>}</>
            ) : (
              <>
                <label>Written by <input name="author" required maxLength={160} /></label>
                <label>When did it happen? <input name="date" type="datetime-local" required /></label>
                <label>Link to the original <input name="reference" type="url" pattern="https://.+" maxLength={1024} required /></label>
                <label>What happened? <textarea name="text" required maxLength={12000} /></label>
              </>
            )}
            <label className="check">
              <input type="checkbox" required /> I have permission to import
              these records.
            </label>
            <button className="button button-blue" disabled={busy}>
              {busy ? "Queuing…" : "Queue import"}
            </button>
          </form>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          {job && (
            <ImportStatus
              api={api}
              key={job}
              id={job}
              refresh={refreshSources}
            />
          )}
        </section>
      )}
    </div>
  );
}

type PublicIssue = Schema["GitHubSnapshot"];

function PublicIssuePreview({ api, sourceId }: { api: Api; sourceId: string }) {
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
  useEffect(() => {
    if (!id) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const job = await api<Schema["JobView"]>(`/jobs/${id}`, {
          signal: controller.signal,
        });
        // Read stages after job state so a terminal poll sees all committed attempts.
        const runs = showRuns
          ? await api<Schema["RunView"][]>(`/jobs/${id}/runs`, {
              signal: controller.signal,
            })
          : undefined;
        if (controller.signal.aborted) return;
        setResult({ job, runs });
        if (["queued", "running", "pending"].includes(job.state))
          timer = setTimeout(poll, 2000);
      } catch (error) {
        if (!controller.signal.aborted) setResult({ error: message(error) });
      }
    };
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [api, id, showRuns]);
  return result;
}

function ImportStatus({
  api,
  id,
  refresh,
}: {
  api: Api;
  id: string;
  refresh: () => void;
}) {
  const result = useJob(api, id);
  const complete = result?.job?.state === "succeeded";
  useEffect(() => {
    if (complete) refresh();
  }, [complete, refresh]);
  if (result?.error)
    return (
      <p role="alert" className="error">
        {result.error}
      </p>
    );
  return (
    <div className="row" role="status">
      <Badge value={result?.job?.phase ?? "pending"} />
      {result?.job?.phase === "waiting_retry" && (
        <span>A temporary interruption occurred. Retrying automatically.</span>
      )}
      {result?.job?.error_code && <span>{label(result.job.error_code)}</span>}
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
                      latest?.status ?? (jobId ? "pending" : "not_started")
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
