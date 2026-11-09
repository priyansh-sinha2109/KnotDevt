"use client";

import { useState } from "react";
import { GitFork } from "lucide-react";
import { type Api, type Schema, label } from "./api";
import { Badge, Empty, Load, Pager, useResource } from "./data";

export function Citation({ evidence }: { evidence: Schema["EvidenceView"] }) {
  return (
    <article className="citation">
      <div className="row">
        <strong>{evidence.original_id}</strong>
        <Badge value={evidence.relation} />
      </div>
      <blockquote>
        <mark>{evidence.excerpt}</mark>
      </blockquote>
      <small>
        {evidence.author} · {new Date(evidence.event_at).toLocaleDateString()} ·
        span {evidence.start}–{evidence.end}
      </small>
      <small className="mono">Revision {evidence.revision_id}</small>
      <small>{evidence.reference}</small>
    </article>
  );
}

export function EvidenceColumn({
  api,
  claimId,
  versionId,
  select,
}: {
  api: Api;
  claimId?: string;
  versionId?: string;
  select?: (id: string) => void;
}) {
  return (
    <aside className="panel evidence-column" aria-label="Evidence Tree">
      <div className="eyebrow">
        <GitFork size={17} /> PROVENANCE
      </div>
      <h2>Evidence Tree</h2>
      {claimId ? (
        <EvidenceDetail
          key={`${claimId}:${versionId ?? ""}`}
          {...{ api, claimId, versionId, select }}
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

function EvidenceDetail({
  api,
  claimId,
  versionId,
  select,
}: {
  api: Api;
  claimId: string;
  versionId?: string;
  select?: (id: string) => void;
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
  );
  const outline = useResource<Schema["EvidenceOutline"]>(
    api,
    mode === "outline" && !versionId ? base + "/outline" + query : "",
  );
  const trace = useResource<Schema["ContextTrace"]>(
    api,
    mode === "trace" || (mode === "outline" && versionId)
      ? base + "/trace" + (versionId ? `?version_id=${versionId}` : "")
      : "",
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
              <ul className="tree">
                {value.branches.map((branch, index) => (
                  <li key={index}>
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
                  {value.selected.evidence.map((evidence, index) => (
                    <Citation key={index} evidence={evidence} />
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
