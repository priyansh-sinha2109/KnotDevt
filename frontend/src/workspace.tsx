"use client";

import { useMemo, useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowRight,
  Bot,
  ClipboardCheck,
  Database,
  FolderKanban,
  GitFork,
  Layers3,
  LayoutGrid,
  LogOut,
  Menu,
  Moon,
  PanelLeftClose,
  ShieldCheck,
  Sun,
} from "lucide-react";
import { ApiError, createApi, message, type Schema } from "./api";
import { Brand, Mark } from "./brand";
import { Badge, Empty, Load, Pager, useResource } from "./data";
import { EvidenceColumn, EvidenceDialog, EvidenceExplorer } from "./evidence";
import { InviteTeammate } from "./invite-teammate";
import { AgentWorkflow, Sources } from "./project-work";
import { Drafts } from "./review";
import { Readiness, Versions } from "./recipient";

const anonymous = createApi();
const navigation = [
  { id: "overview", title: "Overview", icon: LayoutGrid },
  { id: "projects", title: "Projects", icon: FolderKanban },
  { id: "sources", title: "Sources", icon: Database },
  { id: "agents", title: "AI Workflow", icon: Bot },
  { id: "evidence", title: "Evidence", icon: GitFork },
  { id: "review", title: "Review Queue", icon: ShieldCheck },
  { id: "versions", title: "Handover Versions", icon: Layers3 },
  { id: "readiness", title: "Readiness", icon: ClipboardCheck },
];

export default function Workspace() {
  const session = useResource<Schema["SessionView"]>(anonymous, "/auth/me");
  if (!session)
    return (
      <main className="app-loading">
        <Mark /> Recovering your session…
      </main>
    );
  if (session.status === 401)
    return (
      <main className="app-loading">
        <Brand />
        <h1>Sign in to continue</h1>
        <a className="button button-blue" href="/login">
          Login <ArrowRight size={16} />
        </a>
      </main>
    );
  return (
    <Load data={session}>{(value) => <WorkspaceShell session={value} />}</Load>
  );
}

function WorkspaceShell({ session }: { session: Schema["SessionView"] }) {
  const router = useRouter();
  const params = useSearchParams() ?? new URLSearchParams();
  const [expired, setExpired] = useState(false);
  const [logoutError, setLogoutError] = useState("");
  const [announcement, setAnnouncement] = useState("");
  const [dark, setDark] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [workspaceOffset, setWorkspaceOffset] = useState(0);
  const [projectOffset, setProjectOffset] = useState(0);
  const [setupRefresh, setSetupRefresh] = useState(0);
  const [creating, setCreating] = useState(false);
  const [setupError, setSetupError] = useState("");
  const [explorerOpen, setExplorerOpen] = useState(false);
  const [evidenceRefresh, setEvidenceRefresh] = useState(0);
  const api = useMemo(
    () => createApi(session.csrf_token, () => setExpired(true)),
    [session.csrf_token],
  );
  const workspaces = useResource<Schema["Page_WorkspaceView_"]>(
    api,
    `/workspaces?offset=${workspaceOffset}`,
    setupRefresh,
  );
  const workspace =
    workspaces?.value?.items.find(
      (item) => item.id === params.get("workspace"),
    ) ?? workspaces?.value?.items[0];
  const projects = useResource<Schema["Page_ProjectView_"]>(
    api,
    workspace
      ? `/workspaces/${workspace.id}/projects?offset=${projectOffset}`
      : "",
    setupRefresh,
  );
  const project = projects?.value?.items.find(
    (item) => item.id === params.get("project"),
  );
  const reviewer =
    project?.role === "reviewer" || project?.role === "administrator";
  const recipient = project?.role === "recipient";
  const editor = reviewer || project?.role === "contributor";
  const links = navigation.filter(
    ({ id }) =>
      id === "overview" ||
      id === "projects" ||
      (!!project &&
        (id === "sources" ||
          (id === "agents" && editor) ||
          (id === "review" && reviewer) ||
          (["versions", "readiness", "evidence"].includes(id) &&
            (reviewer || recipient)))),
  );
  const view =
    links.find((link) => link.id === params.get("view"))?.id ?? "overview";
  const current = links.find((link) => link.id === view);
  const draftId = params.get("draft") ?? "";
  const versionId = params.get("version") ?? "";
  const rubricId = params.get("rubric") ?? "";
  const attemptId = params.get("attempt") ?? "";
  const jobId = params.get("job") ?? "";
  const claimId = params.get("claim") ?? "";
  const recentDrafts = useResource<Schema["Page_DraftListItem_"]>(api,
    project && reviewer && view === "overview" ? `/projects/${project.id}/drafts?limit=3` : "",
  );
  const recentHandovers = useResource<Schema["Page_VersionListItem_"]>(api,
    project && (reviewer || recipient) && view === "overview" ? `/projects/${project.id}/versions?limit=3` : "",
  );

  function go(
    next: string,
    changes: Record<string, string> = {},
    preserveDetails = false,
  ) {
    const query = new URLSearchParams(params.toString());
    if (workspace) query.set("workspace", workspace.id);
    if (!preserveDetails)
      for (const key of [
        "draft",
        "version",
        "rubric",
        "attempt",
        "job",
        "claim",
      ])
        query.delete(key);
    query.set("view", next);
    for (const [key, value] of Object.entries(changes)) {
      if (value) query.set(key, value);
      else query.delete(key);
    }
    window.history.pushState(null, "", `?${query}`);
  }

  function inspectClaim(next: string, claim: string, version?: string) {
    go(next, { claim, ...(version ? { version } : {}) }, true);
    if (!claim || !window.matchMedia("(max-width: 930px)").matches) return;
    const column = document.getElementById("project-evidence");
    column?.focus({ preventScroll: true });
    column?.scrollIntoView({ block: "start" });
  }

  async function logout() {
    setLogoutError("");
    try {
      await api("/auth/logout", { method: "POST" });
      router.replace("/login");
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 401))
        setLogoutError(message(error));
    }
  }

  async function create(event: FormEvent<HTMLFormElement>, kind: "workspace" | "project") {
    event.preventDefault();
    if (creating || (kind === "project" && workspace?.role !== "administrator")) return;
    const form = event.currentTarget;
    const name = String(new FormData(form).get("name") ?? "").trim();
    if (!name) return;
    setCreating(true);
    setSetupError("");
    try {
      const result = await api<{ id: string }>(kind === "workspace" ? "/workspaces" : `/workspaces/${workspace?.id}/projects`, {
        method: "POST", body: { name },
      });
      form.reset();
      setProjectOffset(0);
      if (kind === "workspace") setWorkspaceOffset(0);
      setSetupRefresh((value) => value + 1);
      go(kind === "workspace" ? "projects" : "overview", kind === "workspace"
        ? { workspace: result.id, project: "" }
        : { project: result.id });
      setAnnouncement(kind === "workspace" ? "Workspace created." : "Project created.");
    } catch (error) {
      setSetupError(message(error));
    } finally {
      setCreating(false);
    }
  }

  async function acceptInvitation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (creating) return;
    const form = event.currentTarget;
    const code = String(new FormData(form).get("code") ?? "").trim();
    if (!/^[A-Za-z0-9_-]{43}$/.test(code)) {
      setSetupError("Paste the full 43-character invitation code. Copy only the code from your invitation.");
      return;
    }
    setCreating(true);
    setSetupError("");
    try {
      const project = await api<Schema["ProjectView"]>("/invitations/redeem", { method: "POST", body: { code } });
      form.reset();
      setWorkspaceOffset(0);
      setProjectOffset(0);
      setSetupRefresh((value) => value + 1);
      go("overview", { workspace: project.workspace_id, project: project.id });
      setAnnouncement("You joined the project.");
    } catch (error) {
      setSetupError(message(error));
    } finally {
      setCreating(false);
    }
  }

  if (expired)
    return (
      <main className="app-loading">
        <Brand />
        <h1>Your session has expired</h1>
        <a className="button button-blue" href="/login">
          Sign in again
        </a>
      </main>
    );
  return (
    <main
      className={`workspace ${dark ? "dark" : ""} ${collapsed ? "collapsed" : ""}`}
    >
      <aside className="sidebar">
        <div className="row spread sidebar-head">
          <Brand />
          <button
            className="icon-button"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-expanded={!collapsed}
            onClick={() => setCollapsed((value) => !value)}
          >
            {collapsed ? <Menu size={18} /> : <PanelLeftClose size={18} />}
          </button>
        </div>
        <div className="sidebar-detail">
          <div className="eyebrow">WORKSPACE</div>
          <Load data={workspaces}>
            {(value) =>
              value.items.length ? (
                <>
                  <select
                    aria-label="Workspace"
                    value={workspace?.id ?? ""}
                    onChange={(event) => {
                      setProjectOffset(0);
                      go("overview", {
                        workspace: event.target.value,
                        project: "",
                      });
                    }}
                  >
                    {value.items.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </select>
                  <Pager
                    offset={workspaceOffset}
                    next={value.next_offset}
                    onChange={(offset) => {
                      setWorkspaceOffset(offset);
                      setProjectOffset(0);
                      go("overview", { workspace: "", project: "" });
                    }}
                  />
                </>
              ) : (
                <Empty>No assigned workspaces.</Empty>
              )
            }
          </Load>
          {workspace && (
            <Load data={projects}>
              {(value) => (
                <>
                  <select
                    aria-label="Project"
                    value={project?.id ?? ""}
                    onChange={(event) =>
                      go("overview", { project: event.target.value })
                    }
                  >
                    <option value="">Select a project</option>
                    {value.items.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </select>
                  <Pager
                    offset={projectOffset}
                    next={value.next_offset}
                    onChange={(offset) => {
                      setProjectOffset(offset);
                      go("projects", { project: "" });
                    }}
                  />
                </>
              )}
            </Load>
          )}
        </div>
        <nav aria-label="Workspace navigation">
          {links.map(({ id, title, icon: Icon }) => (
            <button
              className="nav-item"
              title={title}
              key={id}
              aria-current={view === id ? "page" : undefined}
              onClick={() =>
                go(id, {}, id === "evidence" || id === "readiness")
              }
            >
              <Icon size={17} />
              <span>{title}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <Mark />
          <span>K0.1.0 / KEEP THE THREAD</span>
        </div>
      </aside>
      <div className="workspace-body">
        <header className="app-header">
          <div className="row">
            <span>{workspace?.name ?? "Workspace"}</span>
            <span aria-hidden="true">/</span>
            <strong>{project?.name ?? current?.title}</strong>
          </div>
          <div className="row">
            <button
              className="icon-button"
              aria-label={dark ? "Use light theme" : "Use dark theme"}
              onClick={() => setDark((value) => !value)}
            >
              {dark ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            <span className="account">{session.email}</span>
            <button
              className="icon-button"
              aria-label="Log out"
              onClick={logout}
            >
              <LogOut size={17} />
            </button>
          </div>
        </header>
        {logoutError && (
          <p className="error" role="alert">
            {logoutError}
          </p>
        )}
        {announcement && (
          <div className="workspace-toast row spread">
            <span role="status">{announcement}</span>
            <button
              className="button button-quiet"
              onClick={() => setAnnouncement("")}
            >
              Dismiss
            </button>
          </div>
        )}
        <div
          className={`workspace-grid ${project && (reviewer || recipient) ? "with-evidence" : ""}`}
        >
          <section
            className="workspace-main flow enter"
            key={`${project?.id ?? ""}:${view}`}
          >
            {(view === "overview" || view === "projects") && (
              <>
                <div className="workspace-hero">
                  <div className="eyebrow">
                    <Mark />{" "}
                    {recipient ? "RECIPIENT WORKSPACE" : "HANDOVER WORKSPACE"}
                  </div>
                  <h1>
                    {project?.name ?? workspace?.name ?? "Your workspace"}
                  </h1>
                  <p>
                    {project
                      ? "Keep decisions, evidence and handovers in one place."
                      : workspace
                        ? "Open a project to see its evidence and handover activity."
                        : "Create a workspace to organize your projects and handovers."}
                  </p>
                  {project && <Badge value={project.role} />}
                  {project && view === "overview" && (
                    <div className="row">
                      {editor && <button className="button button-blue" onClick={() => go("sources")}>Add evidence <ArrowRight size={16} /></button>}
                      {workspace?.role === "administrator" && <InviteTeammate api={api} project={project} />}
                      {reviewer && <button className="button" onClick={() => go("review")}>Open review queue</button>}
                      {recipient && <button className="button button-blue" onClick={() => go("versions")}>Open handovers <ArrowRight size={16} /></button>}
                    </div>
                  )}
                </div>
                <details className="panel" open={workspaces?.value?.items.length === 0 || undefined}>
                  <summary>Set up your workspace</summary>
                  <form className="row" onSubmit={(event) => create(event, "workspace")}>
                    <input name="name" aria-label="Workspace name" placeholder="Workspace name" required maxLength={120} />
                    <button className="button button-blue" disabled={creating}>Create workspace</button>
                  </form>
                  {workspace?.role === "administrator" && (
                    <form className="row" onSubmit={(event) => create(event, "project")}>
                      <input name="name" aria-label="Project name" placeholder="Project name" required maxLength={120} />
                      <button className="button button-blue" disabled={creating}>Create project</button>
                    </form>
                  )}
                  <form className="row" onSubmit={acceptInvitation}>
                    <input name="code" type="password" aria-label="Invitation code" placeholder="Invitation code" autoComplete="off" required />
                    <button className="button" disabled={creating}>Join project</button>
                  </form>
                  {setupError && <p role="alert" className="error">{setupError}</p>}
                </details>
                {project && view === "overview" ? (
                  <div className="quick-grid">
                    {links.slice(2).map(({ id, title, icon: Icon }) => (
                      <button
                        className="panel quick-card"
                        key={id}
                        onClick={() => go(id)}
                      >
                        <Icon size={21} />
                        <strong>{title}</strong>
                        <ArrowRight size={17} />
                      </button>
                    ))}
                  </div>
                ) : (
                  workspace && (
                    <section className="panel flow">
                      <h2>Assigned projects</h2>
                      <Load data={projects}>
                        {(value) => (
                          <>
                            {!value.items.length && (
                              <Empty>
                                No projects are assigned to your account in this
                                workspace.
                              </Empty>
                            )}
                            {value.items.map((item) => (
                              <button
                                className="list-item"
                                key={item.id}
                                onClick={() =>
                                  go("overview", { project: item.id })
                                }
                              >
                                <span>
                                  <strong>{item.name}</strong>
                                  <small>{item.role}</small>
                                </span>
                                <ArrowRight size={16} />
                              </button>
                            ))}
                          </>
                        )}
                      </Load>
                    </section>
                  )
                )}
              </>
            )}
            {project && view === "sources" && (
              <Sources api={api} projectId={project.id} editor={editor} />
            )}
            {project && view === "agents" && (
              <AgentWorkflow
                api={api}
                projectId={project.id}
                reviewer={reviewer}
                canAssign={workspace?.role === "administrator"}
                jobId={jobId}
                setJobId={(id) => go("agents", { job: id }, true)}
                openDraft={(id) => go("review", { draft: id })}
              />
            )}
            {project && view === "review" && (
              <Drafts
                api={api}
                projectId={project.id}
                draftId={draftId}
                openDraft={(id) => go("review", { draft: id })}
                selectClaim={(id) => inspectClaim("review", id)}
                exploreClaim={(id) => { go("review", { claim: id }, true); setExplorerOpen(true); }}
                onCorrection={() => setEvidenceRefresh((value) => value + 1)}
                publish={(id) => {
                  go("versions", { version: id });
                  setAnnouncement("Handover version published.");
                }}
              />
            )}
            {project && view === "versions" && (
              <Versions
                api={api}
                projectId={project.id}
                versionId={versionId}
                recipient={recipient}
                openVersion={(id) => go("versions", { version: id })}
                selectClaim={(claim, version) =>
                  inspectClaim("versions", claim, version)
                }
                openRubric={(id) =>
                  go("readiness", { rubric: id, attempt: "" }, true)
                }
              />
            )}
            {project && view === "readiness" && (
              <Readiness
                api={api}
                rubricId={rubricId}
                attemptId={attemptId}
                recipient={recipient}
                openAttempt={(id) => go("readiness", { attempt: id }, true)}
                back={() => go("versions", { version: versionId })}
              />
            )}
            {project && view === "evidence" && (
              <EvidenceExplorer
                api={api}
                projectId={project.id}
                reviewer={reviewer}
                draftId={draftId}
                versionId={versionId}
                claimId={claimId}
                selectPackage={(kind, id) => go("evidence", { [kind]: id })}
                selectClaim={(id) => inspectClaim("evidence", id)}
              />
            )}
          </section>
          {project && (reviewer || recipient) && view === "overview" && (
            <aside className="panel flow" aria-label="Recent handover activity">
              <h2>Recent activity</h2>
              {reviewer && <section className="flow">
                <h3>Drafts</h3>
                <Load data={recentDrafts}>{({ items }) => items.length ? items.map((item) => (
                  <button className="list-item" key={item.id} onClick={() => go("review", { draft: item.id })}>{item.task}</button>
                )) : <Empty>No drafts yet.</Empty>}</Load>
              </section>}
              <section className="flow">
                <h3>Published handovers</h3>
                <Load data={recentHandovers}>{({ items }) => items.length ? items.map((item) => (
                  <button className="list-item" key={item.id} onClick={() => go("versions", { version: item.id })}>{item.task}</button>
                )) : <Empty>No published handovers yet.</Empty>}</Load>
              </section>
            </aside>
          )}
          {project && (reviewer || recipient) && view !== "overview" && (
            <EvidenceColumn
              api={api}
              claimId={reviewer || versionId ? claimId : undefined}
              versionId={versionId}
              select={(id) => inspectClaim(view, id)}
              explore={() => setExplorerOpen(true)}
              refresh={evidenceRefresh}
            />
          )}
          {explorerOpen && claimId && (reviewer || versionId) && (
            <EvidenceDialog api={api} claimId={claimId} draftId={draftId} versionId={versionId || undefined}
              select={(id) => inspectClaim(view, id)} close={() => setExplorerOpen(false)} refresh={evidenceRefresh}
              correct={reviewer && view === "review" ? () => {
                setExplorerOpen(false);
                requestAnimationFrame(() => document.getElementById(`correct-${claimId}`)?.focus());
              } : undefined}
            />
          )}
        </div>
      </div>
    </main>
  );
}
