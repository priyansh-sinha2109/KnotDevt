"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { ArrowRight, FilePlus2, Database, Github, Hash, Layers3, Plus, Search, X, ExternalLink, FileText, ChevronRight, RefreshCw, ShieldCheck } from "lucide-react";
import { evidenceTitle, label, message, type Api, type Schema } from "./api";
import { Badge, Load, Pager, useResource } from "./data";
import { EvidenceColumn } from "./evidence";
import { ImportStatus, PublicIssuePreview } from "./project-work";

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
  const [drawer, setDrawer] = useState(false);
  const [step, setStep] = useState(1);
  const [provider, setProvider] = useState("");
  const [kind, setKind] = useState("");
  const importDialog = useRef<HTMLDialogElement>(null);
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
    `/projects/${projectId}/sources?limit=25&offset=${offset}${search}${provider ? `&provider=${provider}` : ""}${kind ? `&event_type=${kind}` : ""}`,
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
      setStep(3);
    } catch (error) {
      setError(message(error));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => { if (drawer) importDialog.current?.showModal(); }, [drawer]);
  return (
    <div className="sources-workspace flow">
      <header className="sources-heading row spread">
        <div><span className="eyebrow">PROJECT KNOWLEDGE</span><h1>Sources &amp; Integrations</h1><p className="muted">Your project context, connected and traceable.</p></div>
        {editor && <button className="button button-blue" onClick={() => { setStep(1); setJob(""); setError(""); setDrawer(true); }}><Plus size={17} /> Add evidence</button>}
      </header>
      <section className="panel source-library flow" aria-labelledby="source-library-title">
        <header className="row spread"><div className="row"><Database size={20} /><h2 id="source-library-title">Source Library</h2></div><div className="row"><span className="muted source-private"><ShieldCheck size={14} /> Permission-aware evidence</span><button className="button button-quiet" aria-label="Refresh sources" onClick={refreshSources}><RefreshCw size={15} /></button></div></header>
        <div className="source-filters" aria-label="Filter by provider">{["", "manual", "github", "slack", "jira"].map(value => <button key={value} className="source-filter" aria-pressed={provider === value} onClick={() => { setProvider(value); setOffset(0); }}><ProviderIcon provider={value} />{value ? value === "github" ? "GitHub" : value === "slack" ? "Slack" : value === "jira" ? "Jira" : "Manual" : "All sources"}</button>)}</div>
        <form className="source-toolbar" onSubmit={event => { event.preventDefault(); setOffset(0); setQuery(String(new FormData(event.currentTarget).get("query") ?? "").trim()); }}>
          <div className="source-search"><Search size={17} /><input name="query" aria-label="Search permitted sources" placeholder="Search evidence, references or authors…" maxLength={160} /><button className="button button-quiet">Search</button></div>
          <select aria-label="Filter source type" value={kind} onChange={event => { setKind(event.target.value); setOffset(0); }}><option value="">All source types</option>{["task", "implementation", "proposal", "comment", "decision", "meeting", "message"].map(value => <option key={value} value={value}>{label(value)}</option>)}</select>
        </form>
        <Load data={data}>{value => <>
          <div className="source-result-count" role="status">{value.items.length} sources on this page{query ? ` matching “${query}”` : ""}</div>
          {!value.items.length && <div className="source-empty"><Database size={30} /><h3>{query || provider || kind ? "No matching evidence" : "Build your project library"}</h3><p>{query || provider || kind ? "Try another search or filter. Only sources you can access appear here." : "Import a source export, add a note, or connect a project tool."}</p>{editor && <button className="button" onClick={() => { setStep(1); setJob(""); setError(""); setDrawer(true); }}>Add your first source</button>}</div>}
          <div className="source-rows">{value.items.map(item => <article className="source-row" key={item.id}>
            <span className={`provider-icon provider-${item.provider}`}><ProviderIcon provider={item.provider} /></span>
            <button className="source-row-content" aria-label={`Inspect ${evidenceTitle(item.original_id, item.excerpt)}`} onClick={() => setSelected(item.id)}><span className="row source-row-title"><strong>{evidenceTitle(item.original_id, item.excerpt)}</strong><Badge value={item.event_type} /></span><span className="source-excerpt">{item.excerpt}</span><span className="source-meta">{item.provider === "manual" ? "Manual" : label(item.provider)}{item.connection_id ? " · Synced" : item.provider !== "manual" ? " · Provided export" : ""} · {item.author} · <time dateTime={item.event_at}>{new Date(item.event_at).toLocaleString()}</time></span></button>
            <div className="source-row-actions">{item.reference.startsWith("https://") && <a href={item.reference} target="_blank" rel="noopener noreferrer" aria-label={`Open original ${item.original_id}`}><ExternalLink size={16} /></a>}<button aria-label={`Inspect source ${item.original_id}`} onClick={() => setSelected(item.id)}><ChevronRight size={18} /></button></div>
          </article>)}</div><Pager offset={offset} next={value.next_offset} onChange={setOffset} />
        </>}</Load>
      </section>
      <ConnectedTools api={api} projectId={projectId} editor={editor} onBrowse={(value) => { setProvider(value); setOffset(0); }} />
      {selected && (
        <SourceInspector close={() => setSelected("")}>
          <Load data={source}>
            {(value) => (
              <>
                <h2>{evidenceTitle(value.original_id, value.excerpt)}</h2>
                <div className="row">
                  <Badge value={value.policy} />
                  <Badge value={value.kind} />
                </div>
                <p className="source-text">{value.excerpt}</p>
                <small>{value.connection_id ? `Imported from ${value.provider === "github" ? "GitHub" : label(value.provider)}` : value.provider === "manual" ? "Manually provided summary" : "Provided source export"} · Source content still requires evidence review</small>
                <small>{value.reference}</small>
                {editor && /^https:\/\/github\.com\/[^/]+\/[^/]+\/issues\/\d+$/.test(value.reference) && (
                  <PublicIssuePreview key={value.revision_id} api={api} sourceId={value.id} />
                )}
              </>
            )}
          </Load>
          <SourceHistory api={api} sourceId={selected} />
        </SourceInspector>
      )}
      {editor && drawer && (
        <dialog ref={importDialog} className="source-drawer panel flow" aria-labelledby="import-evidence-title" onClose={() => setDrawer(false)}>
          <header className="row spread"><span className="eyebrow">ADD PROJECT CONTEXT</span><button className="button" aria-label="Close import drawer" onClick={() => importDialog.current?.close()}><X size={18} /></button></header>
          <h2 id="import-evidence-title">
            <FilePlus2 size={19} /> Import evidence
          </h2>
          <ol className="import-steps" aria-label="Import steps">{["Choose source", "Add details", "Track import"].map((name, index) => <li key={name} aria-current={step === index + 1 ? "step" : undefined}><span>{index + 1}</span>{name}</li>)}</ol>
          {step < 3 && <form className="flow" onSubmit={importBatch}>
            <div hidden={step !== 1}>
            <label>
              What would you like to add?
              <select value={importMode} onChange={(event) => { setImportMode(event.target.value); setFilePreview(undefined); }}>
                <option value="task">Issue or pending task</option>
                <option value="meeting">Meeting notes</option>
                <option value="message">Team conversation</option>
                <option value="file">Upload a supported source export</option>
              </select>
            </label>
            <p className="muted">Add a focused record or upload a supported JSON export. Imported text stays attributed to its original source.</p>
            <button type="button" className="button button-blue" onClick={() => setStep(2)}>Continue <ArrowRight size={16} /></button></div>
            <fieldset className="flow" hidden={step !== 2} disabled={step !== 2}><legend className="sr-only">Evidence details</legend>
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
            <button type="button" className="button button-quiet" onClick={() => setStep(1)}>Back to source type</button></fieldset>
          </form>}
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
        </dialog>
      )}
      {job && !drawer && <section className="panel"><ImportStatus api={api} id={job} refresh={refreshSources} /></section>}
    </div>
  );
}


function ProviderIcon({ provider }: { provider: string }) {
  if (provider === "github") return <Github size={19} />;
  if (provider === "slack") return <Hash size={19} />;
  if (provider === "jira") return <Layers3 size={19} />;
  if (provider === "manual") return <FileText size={19} />;
  return <Database size={19} />;
}

type Connection = { id: string; status: string; name: string; selected_resources: { id: string; name: string }[]; last_sync_at: string | null; last_attempt_at?: string | null; next_sync_at?: string | null; last_error: string | null; imported_count: number };
type Tool = { provider: string; configured: boolean; setup_message: string | null; connections: Connection[] };
const toolDetails: Record<string, { name: string; description: string; capabilities: string[] }> = {
  github: { name: "GitHub", description: "Repositories, issues and pull requests.", capabilities: ["Issues", "Pull requests", "Commits"] },
  slack: { name: "Slack", description: "Selected public channels and conversations.", capabilities: ["Public channels", "Threads", "Permalinks"] },
  jira: { name: "Jira", description: "Project issues, updates and status history.", capabilities: ["Issues", "Comments", "Changelog"] },
};
function ConnectedTools({ api, projectId, editor, onBrowse }: { api: Api; projectId: string; editor: boolean; onBrowse: (provider: string) => void }) {
  const [refresh, setRefresh] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [managing, setManaging] = useState<{ provider: string; connection: Connection }>();
  const data = useResource<{ items: Tool[] }>(api, `/projects/${projectId}/integrations`, refresh);
  const [returnProvider] = useState(() => typeof window === "undefined" ? null : new URLSearchParams(window.location.search).get("connected"));
  const [returnPickerClosed, setReturnPickerClosed] = useState(false);
  const returnedTool = data?.value?.items.find(item => item.provider === returnProvider);
  const activePicker = managing ?? (!returnPickerClosed && returnedTool?.connections[0]
    ? { provider: returnedTool.provider, connection: returnedTool.connections[0] } : undefined);
  useEffect(() => { const timer = setInterval(() => setRefresh(value => value + 1), 15000); return () => clearInterval(timer); }, []);
  async function action(provider: string, connection?: Connection, command?: string) {
    setBusy(provider); setError("");
    try {
      if (!connection) {
        const result = await api<{ authorization_url: string }>(`/projects/${projectId}/integrations/${provider}/connect`, { method: "POST" });
        window.location.assign(result.authorization_url);
      } else {
        if (command === "disconnect" && !window.confirm("Disconnect this tool? Future synchronization will stop and retained evidence will be hidden.")) return;
        if (command === "share-with-recipients") {
          await api(`/integrations/${connection.id}/share-with-recipients`, { method: "POST" });
        } else {
          await api(`/integrations/${connection.id}/${command}`, { method: "POST" });
        }
        setRefresh(value => value + 1);
      }
    } catch (error) { setError(message(error)); } finally { setBusy(""); }
  }
  return <section className="flow" aria-labelledby="connected-tools-title"><header className="row spread"><div><h2 id="connected-tools-title">Connected tools</h2><p className="muted">Bring in only the repositories, channels and projects you choose.</p></div><div className="row"><span className="source-private"><ShieldCheck size={14} /> Read-only access</span><button className="button button-quiet" aria-label="Refresh connections" onClick={() => setRefresh(value => value + 1)}><RefreshCw size={15} /></button></div></header>
    {error && <p className="error" role="alert">{error}</p>}
    <Load data={data}>{value => <div className="connector-grid">{value.items.map(tool => { const detail = toolDetails[tool.provider] ?? { name: tool.provider, description: "Connected project tool.", capabilities: [] }; return <article className="panel connector-card flow" key={tool.provider}>
      <header className="row spread"><div className="row"><span className={`provider-icon provider-${tool.provider}`}><ProviderIcon provider={tool.provider} /></span><div><h3>{detail.name}</h3><small className="connector-description">{detail.description}</small></div></div><Badge value={tool.connections[0]?.status ?? "not_connected"} /></header>
      <div className="connector-capabilities" aria-label={`${detail.name} capabilities`}>{detail.capabilities.map(capability => <span key={capability}>{capability}</span>)}</div>
      {!tool.connections.length && <div className="connector-empty"><strong>{tool.configured ? "Ready to connect" : "Administrator setup required"}</strong><small>{tool.setup_message ?? "Authorize your account to choose only the resources you need."}</small></div>}
      {tool.connections.map(connection => <div className="flow" key={connection.id}><strong>{connection.name}</strong><small>{connection.selected_resources.length ? connection.selected_resources.map(resource => resource.name).join(", ") : "No resources selected — choose resources in Manage to start sync."}</small><small>{connection.last_sync_at ? `Last synced ${new Date(connection.last_sync_at).toLocaleString()}` : "No completed sync"} · {connection.imported_count} imported records</small>{connection.last_attempt_at && <small>Last attempted {new Date(connection.last_attempt_at).toLocaleString()}</small>}{connection.next_sync_at && <small>Next sync {new Date(connection.next_sync_at).toLocaleString()}</small>}{connection.last_error && <p className="error">{connection.last_error}</p>}<div className="row"><button className="button" disabled={!editor || !!busy || !connection.selected_resources.length || connection.status === "syncing"} onClick={() => action(tool.provider, connection, "sync")}><RefreshCw size={14} /> Sync</button><button className="button button-quiet" disabled={!editor} onClick={() => setManaging({ provider: tool.provider, connection })}>Manage</button><button className="link-button" onClick={() => onBrowse(tool.provider)}>View evidence</button></div><div className="row"><button className="link-button" disabled={!editor || !!busy} onClick={() => action(tool.provider, connection, "share-with-recipients")}>Share with recipients</button><button className="link-button" disabled={!editor || !!busy || !tool.configured} onClick={() => action(tool.provider)}>Reauthorize</button><button className="link-button" disabled={!editor || !!busy} onClick={() => action(tool.provider, connection, "disconnect")}>Disconnect</button></div></div>)}
      {!tool.connections.length && <div className="connector-actions"><button className="button button-blue" disabled={!editor || !tool.configured || !!busy} onClick={() => action(tool.provider)}>{busy === tool.provider ? "Connecting…" : tool.configured ? `Connect ${detail.name}` : "Setup required"}<ArrowRight size={14} /></button>{!editor && <small className="muted">Editor permission is required to connect a tool.</small>}</div>}
    </article>; })}</div>}</Load>
    {activePicker && <SourceInspector close={() => { setManaging(undefined); setReturnPickerClosed(true); }}><ResourcePicker api={api} connection={activePicker.connection} done={() => { setManaging(undefined); setReturnPickerClosed(true); setRefresh(value => value + 1); }} /></SourceInspector>}
  </section>;
}
function ResourcePicker({ api, connection, done }: { api: Api; connection: Connection; done: () => void }) {
  const data = useResource<{ items: { id: string; name: string }[] }>(api, `/integrations/${connection.id}/resources`);
  const [selected, setSelected] = useState(connection.selected_resources.map(value => value.id));
  const [error, setError] = useState("");
  return <><h2>Choose permitted resources</h2><p>Evidence is restricted to the connecting user. Direct messages and private Slack channels are excluded.</p><Load data={data}>{value => <form className="flow" onSubmit={async event => { event.preventDefault(); try { await api(`/integrations/${connection.id}/resources`, { method: "POST", body: { resource_ids: selected } }); done(); } catch (error) { setError(message(error)); } }}>{value.items.map(resource => <label className="check" key={resource.id}><input type="checkbox" checked={selected.includes(resource.id)} onChange={event => setSelected(old => event.target.checked ? [...old, resource.id] : old.filter(id => id !== resource.id))} />{resource.name}</label>)}<button className="button button-blue">Save selection</button></form>}</Load>{error && <p className="error" role="alert">{error}</p>}</>;
}
function SourceInspector({ children, close }: { children: ReactNode; close: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { dialog.current?.showModal(); }, []);
  return <dialog ref={dialog} className="source-drawer panel flow" aria-label="Source and integration inspector" onClose={close}><header className="row spread"><span className="eyebrow">PROVENANCE &amp; DETAILS</span><button className="button" aria-label="Close inspector" onClick={() => dialog.current?.close()}><X size={18} /></button></header>{children}</dialog>;
}
function SourceHistory({ api, sourceId }: { api: Api; sourceId: string }) {
  const [claimId, setClaimId] = useState("");
  const claims = useResource<{items: {id: string; statement: string}[]}>(api, `/sources/${sourceId}/claims`);
  const revisions = useResource<{ items: Schema["SourceView"][] }>(api, `/sources/${sourceId}/revisions`);
  const [selected, setSelected] = useState<Schema["SourceView"]>();
  return <section className="flow"><h3>Revision history</h3><Load data={revisions}>{value => value.items.map((revision, index) => <button className="list-item" key={revision.revision_id} onClick={() => setSelected(revision)}><span>{index === 0 ? "Latest snapshot" : "Earlier snapshot"}<small>{new Date(revision.imported_at).toLocaleString()}</small></span><ChevronRight size={16} /></button>)}</Load>{selected && <div className="panel flow"><h3>Exact retained revision</h3><small>Fingerprint {selected.content_hash}</small><p className="source-text">{selected.excerpt}</p></div>}<h3>Claims citing this source</h3><Load data={claims}>{value => value.items.length ? value.items.map(claim => <button className="list-item" key={claim.id} onClick={() => setClaimId(claim.id)}>{claim.statement}</button>) : <p className="muted">No visible claims cite this source yet. A source snapshot alone does not verify a claim.</p>}</Load>{claimId && <EvidenceColumn api={api} claimId={claimId} select={setClaimId} />}</section>;
}
