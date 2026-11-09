"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  ArrowRight,
  Bot,
  Check,
  CircleDashed,
  FilePlus2,
  ScanSearch,
} from "lucide-react";
import { label, message, type Api, type Schema } from "./api";
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
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
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
    const raw = String(new FormData(form).get("batch"));
    setError("");
    setBusy(true);
    try {
      const body = JSON.parse(raw);
      const entries =
        body?.kind === "issue-events"
          ? body.events
          : body?.kind === "conversation-notes"
            ? body.notes
            : undefined;
      if (
        typeof body?.provider !== "string" ||
        !Array.isArray(entries) ||
        !entries.length
      )
        throw new Error(
          "Supply an issue-events or conversation-notes batch with a provider and at least one entry.",
        );
      if (new TextEncoder().encode(JSON.stringify(body)).length > 1048576)
        throw new Error("Import exceeds the 1 MiB limit.");
      if (retry.current.text !== raw)
        retry.current = { text: raw, key: crypto.randomUUID() };
      const queued = await api<Schema["JobView"]>(
        `/projects/${projectId}/imports`,
        { method: "POST", body, key: retry.current.key },
      );
      setJob(queued.id);
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
                    <strong>{item.original_id}</strong>
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
                <h2>{value.original_id}</h2>
                <div className="row">
                  <Badge value={value.policy} />
                  <Badge value={value.kind} />
                </div>
                <p className="source-text">{value.excerpt}</p>
                <small className="mono">Revision {value.revision_id}</small>
                <small>{value.reference}</small>
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
          <p>
            Paste a supported issue-events or conversation-notes JSON batch.
          </p>
          <form className="flow" onSubmit={importBatch}>
            <label>
              JSON batch
              <textarea
                name="batch"
                required
                spellCheck={false}
                className="mono"
                placeholder='{"kind":"issue-events","provider":"manual","events":[…]}'
              />
            </label>
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
              refresh={() => setRefresh((value) => value + 1)}
            />
          )}
        </section>
      )}
    </div>
  );
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
  if (result?.error)
    return (
      <p role="alert" className="error">
        {result.error}
      </p>
    );
  return (
    <div className="row" role="status">
      <Badge value={result?.job?.state ?? "pending"} />
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
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const audience = String(fields.get("audience"))
      .split(/[\s,]+/)
      .filter(Boolean);
    if (
      !audience.length ||
      audience.length > 8 ||
      audience.some(
        (id) => !/^[\da-f]{8}(?:-[\da-f]{4}){3}-[\da-f]{12}$/i.test(id),
      )
    ) {
      setError("Enter one to eight assigned recipient UUIDs.");
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
          <label>
            Assigned recipient IDs
            <input
              name="audience"
              required
              placeholder="Comma-separated user UUIDs"
            />
          </label>
          <small>
            Recipients can find their account ID in the workspace header.
          </small>
          <button className="button button-blue" disabled={busy}>
            {busy ? "Queuing…" : "Run workflow"}
            <ArrowRight size={16} />
          </button>
        </form>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <details>
          <summary>Open an existing job</summary>
          <form
            className="row"
            onSubmit={(event) => {
              event.preventDefault();
              setJobId(
                String(new FormData(event.currentTarget).get("job")).trim(),
              );
            }}
          >
            <input
              aria-label="Job ID"
              name="job"
              required
              placeholder="Job UUID"
            />
            <button className="button button-quiet">Open</button>
          </form>
        </details>
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
        {data?.job && <Badge value={data.job.state} />}
      </div>
      {jobId && <small className="mono">Job {jobId}</small>}
      {(error || data?.error) && (
        <p className="error" role="alert">
          {error || data?.error}
        </p>
      )}
      {data?.job?.error_code && (
        <p className="error">{label(data.job.error_code)}</p>
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
                  <Badge value={latest?.status ?? "pending"} />
                </div>
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
      {data?.job?.state === "succeeded" && (
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
