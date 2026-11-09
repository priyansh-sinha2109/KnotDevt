"use client";

import { useMemo, useState } from "react";
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
import { EvidenceColumn } from "./evidence";
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
  const [dark, setDark] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [workspaceOffset, setWorkspaceOffset] = useState(0);
  const [projectOffset, setProjectOffset] = useState(0);
  const api = useMemo(
    () => createApi(session.csrf_token, () => setExpired(true)),
    [session.csrf_token],
  );
  const workspaces = useResource<Schema["Page_WorkspaceView_"]>(
    api,
    `/workspaces?offset=${workspaceOffset}`,
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
            <details className="account">
              <summary>{session.email}</summary>
              <small className="mono">Account ID: {session.user_id}</small>
            </details>
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
                      : "Choose an assigned project to see its handover activity."}
                  </p>
                  {project && <Badge value={project.role} />}
                </div>
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
                selectClaim={(id) => go("review", { claim: id }, true)}
                publish={(id) => go("versions", { version: id })}
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
                  go("versions", { claim, version }, true)
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
              <section className="panel flow">
                <h2>Evidence explorer</h2>
                <p>
                  Inspect claims and source revisions from the Evidence Tree
                  beside this panel.
                </p>
                <button
                  className="button button-quiet"
                  onClick={() => go(reviewer ? "review" : "versions")}
                >
                  {reviewer ? "Open review queue" : "Open handovers"}
                </button>
              </section>
            )}
          </section>
          {project && (reviewer || recipient) && (
            <EvidenceColumn
              api={api}
              claimId={claimId}
              versionId={versionId}
              select={(id) => go(view, { claim: id }, true)}
            />
          )}
        </div>
      </div>
    </main>
  );
}
