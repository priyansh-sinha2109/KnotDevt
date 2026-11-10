"use client";

import { useEffect, useRef, useState } from "react";
import { GitFork } from "lucide-react";
import { type Api, type Schema, evidenceTitle, label } from "./api";
import { Badge, Empty, Load, Pager, useResource } from "./data";
import { EvidenceGraph } from "./evidence-graph";

export function EvidenceExplorer({
  api,
  projectId,
  reviewer,
  draftId,
  versionId,
  claimId,
  selectPackage,
  selectClaim,
}: {
  api: Api;
  projectId: string;
  reviewer: boolean;
  draftId: string;
  versionId: string;
  claimId: string;
  selectPackage: (kind: "draft" | "version", id: string) => void;
  selectClaim: (id: string) => void;
}) {
  const [offset, setOffset] = useState(0);
  const [mode, setMode] = useState<"draft" | "version">(
    draftId && !versionId ? "draft" : "version",
  );
  const type = reviewer
    ? draftId
      ? "draft"
      : versionId
        ? "version"
        : mode
    : "version";
  const id = type === "draft" ? draftId : versionId;
  const list = useResource<
    Schema["Page_DraftListItem_"] | Schema["Page_VersionListItem_"]
  >(api, !id ? `/projects/${projectId}/${type}s?offset=${offset}` : "");
  const draft = useResource<Schema["DraftView"]>(
    api,
    type === "draft" && id ? `/drafts/${id}` : "",
  );
  const version = useResource<Schema["VersionView"]>(
    api,
    type === "version" && id ? `/versions/${id}` : "",
  );

  function claimList(claims: Schema["ClaimSummary"][]) {
    return claims.length ? (
      claims.map((claim) => (
        <button
          className="list-item"
          key={claim.id}
          aria-pressed={claim.id === claimId}
          onClick={() => selectClaim(claim.id)}
        >
          <span>
            <strong>{claim.statement}</strong>
            <small>
              {label(claim.kind)} · {label(claim.status)}
            </small>
          </span>
          <GitFork size={16} />
        </button>
      ))
    ) : (
      <Empty>This package has no visible claims.</Empty>
    );
  }

  return (
    <section className="panel flow">
      <h2>Evidence explorer</h2>
      <p>
        Choose a package and claim to inspect citations, related claims and
        Context Trace.
      </p>
      {reviewer && (
        <div className="tabs" aria-label="Evidence packages">
          {(["version", "draft"] as const).map((kind) => (
            <button
              key={kind}
              aria-pressed={type === kind}
              onClick={() => {
                setMode(kind);
                setOffset(0);
                selectPackage(kind, "");
              }}
            >
              {kind === "version" ? "Published versions" : "Review drafts"}
            </button>
          ))}
        </div>
      )}
      {id && (
        <button className="back-button" onClick={() => selectPackage(type, "")}>
          ← Choose another package
        </button>
      )}
      {!id && (
        <Load data={list}>
          {(value) => (
            <>
              {value.items.length === 0 && (
                <Empty>
                  No {type === "draft" ? "review drafts" : "published versions"}{" "}
                  are visible.
                </Empty>
              )}
              {value.items.map((item) => (
                <button
                  className="list-item"
                  key={item.id}
                  onClick={() => selectPackage(type, item.id)}
                >
                  <span>
                    <strong>{item.task}</strong>
                    <small>
                      {"revision" in item
                        ? `Draft revision ${item.revision}`
                        : `Version ${item.number}`}
                    </small>
                  </span>
                  <GitFork size={16} />
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
      )}
      {type === "draft" && id && (
        <Load data={draft}>
          {(value) =>
            value.project_id === projectId ? (
              <>
                <h3>{value.task}</h3>
                {claimList(value.claims.map((item) => item.claim))}
              </>
            ) : (
              <Empty>This draft belongs to another project.</Empty>
            )
          }
        </Load>
      )}
      {type === "version" && id && (
        <Load data={version}>
          {(value) => (
            <>
              <Badge value={value.status} />
              {value.handover?.project_id === projectId ? (
                <>
                  <h3>{value.handover.task}</h3>
                  {claimList(value.handover.claims)}
                </>
              ) : (
                <Empty>This version is unavailable in this project.</Empty>
              )}
            </>
          )}
        </Load>
      )}
    </section>
  );
}

export function Citation({ evidence }: { evidence: Schema["EvidenceView"] }) {
  return (
    <article className="citation">
      <div className="row">
        <strong>{evidenceTitle(evidence.original_id, evidence.excerpt)}</strong>
        <Badge value={evidence.relation} />
      </div>
      <blockquote>
        <mark>{evidence.excerpt}</mark>
      </blockquote>
      <small>
        {evidence.author} · {new Date(evidence.event_at).toLocaleDateString()} ·
        span {evidence.start}–{evidence.end}
      </small>
      <small>{evidence.provider === "manual" ? "Manually provided summary" : "Provided source snapshot"} · Original source not independently checked</small>
      {evidence.reference.startsWith("https://") ? (
        <a href={evidence.reference} target="_blank" rel="noopener noreferrer">Open original reference</a>
      ) : <small>{evidence.reference}</small>}
    </article>
  );
}

export function EvidenceColumn({
  api,
  claimId,
  versionId,
  select,
  explore,
  refresh = 0,
}: {
  api: Api;
  claimId?: string;
  versionId?: string;
  select?: (id: string) => void;
  explore?: () => void;
  refresh?: number;
}) {
  return (
    <aside
      className="panel evidence-column"
      aria-label="Evidence Tree"
      id="project-evidence"
      tabIndex={-1}
    >
      <div className="eyebrow">
        <GitFork size={17} /> PROVENANCE
      </div>
      <h2>Evidence Tree</h2>
      {claimId && explore && <button className="button button-blue" onClick={explore}>Explore Evidence</button>}
      {claimId ? (
        <EvidenceDetail
          key={`${claimId}:${versionId ?? ""}`}
          {...{ api, claimId, versionId, select, refresh }}
        />
      ) : (
        <Empty>
          Select a claim in a draft or handover to inspect its evidence and
          relationships.
        </Empty>
      )}
    </aside>
  );
}

export function EvidenceDialog({ api, claimId, draftId, versionId, select, close, refresh, correct }: {
  api: Api;
  claimId: string;
  draftId: string;
  versionId?: string;
  select: (id: string) => void;
  close: () => void;
  refresh: number;
  correct?: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [showNavigator, setShowNavigator] = useState(false);
  const draft = useResource<Schema["DraftView"]>(api, draftId && !versionId ? `/drafts/${draftId}` : "", refresh);
  useEffect(() => { dialog.current?.showModal(); }, []);
  const current = draft?.value?.claims.find(({ claim }) => claim.id === claimId);
  return (
    <dialog ref={dialog} className="evidence-workbench panel" aria-labelledby="evidence-workbench-title" onClose={close}>
      <header className="row spread">
        <div><span className="eyebrow">KnotDevt · Provenance</span><h2 id="evidence-workbench-title">Evidence Explorer</h2></div>
        <button className="button" onClick={() => dialog.current?.close()}>Close explorer</button>
      </header>
      <div className="evidence-workbench-body">
        <aside className="flow evidence-claim-nav" aria-label="Claim navigation">
          <button className="button evidence-mobile-navigator" aria-expanded={showNavigator} aria-controls="evidence-claim-nav-content" onClick={() => setShowNavigator(!showNavigator)}>
            {showNavigator ? "Hide claim navigator" : "Show claim navigator"}
          </button>
          <div className="flow evidence-claim-nav-content" id="evidence-claim-nav-content" data-expanded={showNavigator}>
          <h3>Claim navigator</h3>
          {current && <><Badge value={current.claim.kind} /><p>{current.claim.statement}</p>
            <small>{current.flags.length ? "Review needed" : "Check meaning against the cited text"}</small></>}
          {current && correct && <button className="button" onClick={correct}>Return to claim correction</button>}
          {!!draft?.value?.claims.length && <label>Choose a claim
            <select value={claimId} onChange={(event) => select(event.target.value)}>
              {draft.value.claims.map(({ claim }, index) => <option key={claim.id} value={claim.id}>{index + 1}. {claim.statement.slice(0, 100)}</option>)}
            </select>
          </label>}
          <h3>Relationships</h3>
          <ul className="outline"><li>Supports · evidence for a claim</li><li>Contradicts · evidence against a claim</li><li>Requires · a dependency</li><li>Supersedes · replaces an earlier claim</li><li>Context · background only</li></ul>
          </div>
        </aside>
        <EvidenceDetail key={`${claimId}:${versionId ?? ""}`} {...{ api, claimId, versionId, select, refresh }} large />
      </div>
    </dialog>
  );
}

function EvidenceDetail({
  api,
  claimId,
  versionId,
  select,
  large = false,
  refresh = 0,
}: {
  api: Api;
  claimId: string;
  versionId?: string;
  select?: (id: string) => void;
  large?: boolean;
  refresh?: number;
}) {
  const [mode, setMode] = useState<"tree" | "trace" | "outline">(
    versionId ? "trace" : "tree",
  );
  const [offset, setOffset] = useState(0);
  const base = `/claims/${claimId}`;
  const query = `?offset=${offset}&limit=25`;
  const tree = useResource<Schema["EvidenceTree"]>(
    api,
    mode === "tree" ? base + "/tree" + query : "",
    refresh,
  );
  const outline = useResource<Schema["EvidenceOutline"]>(
    api,
    mode === "outline" && !versionId ? base + "/outline" + query : "",
    refresh,
  );
  const trace = useResource<Schema["ContextTrace"]>(
    api,
    mode === "trace" || (mode === "outline" && versionId)
      ? base + "/trace" + (versionId ? `?version_id=${versionId}` : "")
      : "",
    refresh,
  );
  const tabs = versionId
    ? (["trace", "outline"] as const)
    : (["tree", "trace", "outline"] as const);
  return (
    <div className="flow">
      <div className="tabs" aria-label="Evidence views">
        {tabs.map((tab) => (
          <button
            key={tab}
            aria-pressed={mode === tab}
            onClick={() => {
              setOffset(0);
              setMode(tab);
            }}
          >
            {tab === "trace" ? "Context Trace" : label(tab)}
          </button>
        ))}
      </div>
      {mode === "tree" && (
        <Load data={tree}>
          {(value) => (
            <>
              <div className="claim-root">
                <Badge value={value.root.status} />
                <h3>{value.root.statement}</h3>
              </div>
              {!!value.branches.length && <EvidenceGraph tree={value} large={large} renderDetails={large ? (branches) => (
                <aside className="panel flow evidence-node-detail" aria-label="Selected node details">
                  <h3>Selected node</h3>
                  {branches.length ? branches.map((branch, index) => branch.evidence
                    ? <Citation key={index} evidence={branch.evidence} />
                    : branch.related_claim && <div key={index}><Badge value={branch.related_claim.relation} /><p>{branch.related_claim.claim.statement}</p><button className="button" onClick={() => select?.(branch.related_claim!.claim.id)}>Focus related claim</button></div>
                  ) : <><p>{value.root.statement}</p><small>{new Set(value.branches.flatMap(({ evidence }) => evidence ? [evidence.revision_id] : [])).size} cited source snapshots on this page</small><p>Select a source to read its exact quote. An exact span still needs a review of meaning.</p></>}
                </aside>
              ) : undefined} />}
              <ul className="tree" aria-label="Evidence text outline">
                {value.branches.map((branch, index) => (
                  <li key={index} id={`evidence-branch-${index}`}>
                    {branch.evidence && <Citation evidence={branch.evidence} />}
                    {branch.related_claim && (
                      <button
                        className="link-button"
                        onClick={() => select?.(branch.related_claim!.claim.id)}
                      >
                        <Badge value={branch.related_claim.relation} />{" "}
                        {branch.related_claim.claim.statement}
                      </button>
                    )}
                  </li>
                ))}
              </ul>
              {!value.branches.length && (
                <Empty>No visible supporting evidence or related claims.</Empty>
              )}
              <Pager
                offset={offset}
                next={value.next_offset}
                onChange={setOffset}
              />
            </>
          )}
        </Load>
      )}
      {mode === "outline" && !versionId && (
        <Load data={outline}>
          {(value) => (
            <>
              <ul className="outline">
                {value.lines.map((line, index) => (
                  <li key={index}>{line}</li>
                ))}
              </ul>
              <Pager
                offset={offset}
                next={value.next_offset}
                onChange={setOffset}
              />
            </>
          )}
        </Load>
      )}
      {(mode === "trace" || (mode === "outline" && versionId)) && (
        <Load data={trace}>
          {(value) => (
            <>
              <Badge value={value.status} />
              {!value.selected ? (
                <Empty>This evidence snapshot is unavailable.</Empty>
              ) : mode === "outline" ? (
                <ol className="outline">
                  {value.outline?.map((line, index) => (
                    <li key={index}>{line}</li>
                  ))}
                </ol>
              ) : (
                <>
                  <h3>{value.selected.claim.statement}</h3>
                  {value.selected.evidence.length > 0 && <EvidenceGraph large={large} renderDetails={large ? (branches) => (
                    <aside className="panel flow evidence-node-detail" aria-label="Selected node details"><h3>Selected node</h3>
                      {branches.length ? branches.map(({ evidence }, index) => evidence && <Citation key={index} evidence={evidence} />) : <p>Select a source to inspect its citation.</p>}
                    </aside>
                  ) : undefined} tree={{
                    root: value.selected.claim,
                    branches: value.selected.evidence.map((evidence) => ({ evidence })),
                    next_offset: null,
                  }} />}
                  {value.selected.evidence.map((evidence, index) => (
                    <div key={index} id={`evidence-branch-${index}`}><Citation evidence={evidence} /></div>
                  ))}
                  <ol className="trace-list">
                    {value.timeline?.map((item) => (
                      <li key={item.claim.id}>
                        <Badge value={item.claim.status} />
                        <h4>{item.claim.statement}</h4>
                        {item.evidence.map((evidence, index) => (
                          <Citation key={index} evidence={evidence} />
                        ))}
                      </li>
                    ))}
                  </ol>
                  {value.relationships?.map((edge) => (
                    <small
                      key={`${edge.origin_id}:${edge.target_id}:${edge.relation}`}
                    >
                      <Badge value={edge.relation} />{" "}
                      {value.timeline?.find(
                        (item) => item.claim.id === edge.target_id,
                      )?.claim.statement ?? "Related claim"}
                    </small>
                  ))}
                  {value.unresolved?.map((item) => (
                    <p className="notice" key={item}>
                      {item}
                    </p>
                  ))}
                </>
              )}
            </>
          )}
        </Load>
      )}
    </div>
  );
}
