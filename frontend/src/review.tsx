"use client";

import { useState, type FormEvent } from "react";
import { ArrowRight, ShieldCheck, TriangleAlert } from "lucide-react";
import { label, message, type Api, type Schema } from "./api";
import { Badge, Empty, Load, Pager, useResource } from "./data";

const classifications = [
  "prerequisite",
  "blocker",
  "approval",
  "ownership",
  "non_critical",
] as const;
const kinds = [
  "overview",
  "decision",
  "work_item",
  "owner",
  "contact",
  "prerequisite",
  "blocker",
  "risk",
  "next_action",
] as const;
const statuses = [
  "unverified",
  "proposed",
  "accepted",
  "implemented",
  "conflicting",
  "open",
  "confirmed",
  "suggested",
  "unresolved",
  "resolved",
  "rejected",
] as const;
const citationFlags = [
  "invalid_or_ambiguous_citation",
  "supporting_evidence_missing",
  "contradictory_evidence",
];
type Draft = Schema["DraftView"];
type Gap = Schema["ClaimGapReview"];

export function Drafts({
  api,
  projectId,
  draftId,
  openDraft,
  selectClaim,
  publish,
}: {
  api: Api;
  projectId: string;
  draftId: string;
  openDraft: (id: string) => void;
  selectClaim: (id: string) => void;
  publish: (id: string) => void;
}) {
  const [offset, setOffset] = useState(0);
  const [refresh, setRefresh] = useState(0);
  const list = useResource<Schema["Page_DraftListItem_"]>(
    api,
    !draftId ? `/projects/${projectId}/drafts?offset=${offset}` : "",
  );
  const draft = useResource<Draft>(
    api,
    draftId ? `/drafts/${draftId}` : "",
    refresh,
  );
  return draftId ? (
    <div className="flow">
      <button className="back-button" onClick={() => openDraft("")}>
        ← Review queue
      </button>
      <Load data={draft}>
        {(value) =>
          value.project_id === projectId ? (
            <DraftReview
              key={`${value.id}:${value.revision}`}
              {...{ api, draft: value, selectClaim, publish }}
              reload={() => {
                selectClaim("");
                setRefresh((n) => n + 1);
              }}
            />
          ) : (
            <Empty>This draft belongs to another project.</Empty>
          )
        }
      </Load>
    </div>
  ) : (
    <section className="panel flow">
      <h2>Review queue</h2>
      <Load data={list}>
        {(value) => (
          <>
            {!value.items.length && (
              <Empty>Run the workflow to generate a draft for review.</Empty>
            )}
            {value.items.map((item) => (
              <button
                className="list-item"
                key={item.id}
                onClick={() => openDraft(item.id)}
              >
                <span>
                  <strong>{item.task}</strong>
                  <small>Draft revision {item.revision}</small>
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
  );
}

function DraftReview({
  api,
  draft,
  selectClaim,
  publish,
  reload,
}: {
  api: Api;
  draft: Draft;
  selectClaim: (id: string) => void;
  publish: (id: string) => void;
  reload: () => void;
}) {
  const [decisions, setDecisions] = useState<Record<string, Partial<Gap>>>({});
  const [gaps, setGaps] = useState<Schema["AdditionalGap"][]>([]);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [correction, setCorrection] = useState("");
  const complete =
    draft.claims.every(({ claim }) => {
      const gap = decisions[claim.revision_id];
      return gap?.classification && gap.disposition && gap.rationale?.trim();
    }) && gaps.every((gap) => gap.rationale.trim() && gap.source_revision_id);

  function update(id: string, value: Partial<Gap>) {
    setDecisions((previous) => ({
      ...previous,
      [id]: { ...previous[id], ...value },
    }));
  }

  async function approve(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!confirmed || !complete || busy) return;
    setBusy(true);
    setError("");
    try {
      const claims = draft.claims.map(({ claim }) => {
        const { classification, disposition, rationale } =
          decisions[claim.revision_id];
        if (!classification || !disposition || !rationale?.trim())
          throw new Error("Review every claim revision.");
        return {
          claim_revision_id: claim.revision_id,
          classification,
          disposition,
          rationale: rationale.trim(),
        };
      });
      const body = {
        expected_revision: draft.revision,
        rubric: draft.proposed_rubric,
        critical_gap_review: {
          reviewed_source_revision_ids: draft.source_revision_ids,
          claims,
          additional_gaps: gaps,
        },
      } satisfies Schema["ApprovalInput"];
      const version = await api<Schema["VersionView"]>(
        `/drafts/${draft.id}/approve`,
        { method: "POST", body },
      );
      publish(version.id);
    } catch (error) {
      setError(message(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="flow">
      <div className="panel flow">
        <div className="eyebrow">
          <ShieldCheck size={17} /> HUMAN CHECKPOINT
        </div>
        <h2>{draft.task}</h2>
        <p>
          Draft revision {draft.revision} · {draft.claims.length} claims ·{" "}
          {draft.source_revision_ids.length} source revisions
        </p>
        {draft.unresolved.map((item) => (
          <p className="notice" key={item}>
            <TriangleAlert size={16} /> {item}
          </p>
        ))}
      </div>
      {draft.claims.map((item) => {
        const claim = item.claim;
        return (
          <article className="panel flow" key={claim.revision_id}>
            <div className="row">
              <Badge value={claim.kind} />
              <Badge value={claim.status} />
            </div>
            <h3>{claim.statement}</h3>
            {item.flags.length > 0 && (
              <div className="row">
                {item.flags.map((flag) => (
                  <Badge key={flag} value={flag} />
                ))}
              </div>
            )}
            {item.reviewer_note && <p>Reviewer note: {item.reviewer_note}</p>}
            <div className="row">
              <button
                className="button button-quiet"
                onClick={() => selectClaim(claim.id)}
              >
                Inspect evidence
              </button>
              <button
                className="button button-quiet"
                onClick={() =>
                  setCorrection(correction === claim.id ? "" : claim.id)
                }
              >
                Correct claim
              </button>
            </div>
            {correction === claim.id && (
              <Correction {...{ api, draft, claim, reload }} />
            )}
          </article>
        );
      })}
      <form className="panel flow" onSubmit={approve}>
        <h2>Critical-gap review</h2>
        <p>
          Confirm a classification, disposition and rationale for every current
          claim revision.
        </p>
        {draft.claims.map(({ claim, flags }, index) => {
          const value = decisions[claim.revision_id] ?? {};
          const critical = ["prerequisite", "blocker"].includes(claim.kind);
          const canResolve =
            claim.status === "resolved" &&
            !flags.some((flag) => citationFlags.includes(flag));
          return (
            <fieldset className="gap-form" key={claim.revision_id}>
              <legend>
                {index + 1}. {claim.statement}
              </legend>
              <div className="form-columns">
                <label>
                  Classification
                  <select
                    required
                    value={value.classification ?? ""}
                    onChange={(event) => {
                      const classification = event.target
                        .value as Gap["classification"];
                      update(claim.revision_id, {
                        classification,
                        disposition:
                          classification === "non_critical"
                            ? "non_blocking"
                            : undefined,
                      });
                    }}
                  >
                    <option value="">Choose classification</option>
                    {classifications
                      .filter((item) => !critical || item !== "non_critical")
                      .map((item) => (
                        <option key={item} value={item}>
                          {label(item)}
                        </option>
                      ))}
                  </select>
                </label>
                <label>
                  Disposition
                  <select
                    required
                    value={value.disposition ?? ""}
                    onChange={(event) =>
                      update(claim.revision_id, {
                        disposition: event.target.value as Gap["disposition"],
                      })
                    }
                  >
                    <option value="">Choose disposition</option>
                    {(value.classification === "non_critical"
                      ? ["non_blocking"]
                      : [
                          "blocking",
                          "unverified",
                          ...(canResolve ? ["resolved"] : []),
                        ]
                    ).map((item) => (
                      <option key={item} value={item}>
                        {label(item)}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <label>
                Rationale
                <input
                  required
                  maxLength={500}
                  value={value.rationale ?? ""}
                  onChange={(event) =>
                    update(claim.revision_id, { rationale: event.target.value })
                  }
                />
              </label>
            </fieldset>
          );
        })}
        {gaps.map((gap, index) => (
          <fieldset key={index} className="gap-form">
            <legend>Additional gap {index + 1}</legend>
            <div className="form-columns">
              <label>
                Classification
                <select
                  value={gap.classification}
                  onChange={(event) =>
                    setGaps((items) =>
                      items.map((item, i) =>
                        i === index
                          ? {
                              ...item,
                              classification: event.target
                                .value as typeof gap.classification,
                            }
                          : item,
                      ),
                    )
                  }
                >
                  {classifications.slice(0, -1).map((item) => (
                    <option key={item}>{item}</option>
                  ))}
                </select>
              </label>
              <label>
                Disposition
                <select
                  value={gap.disposition}
                  onChange={(event) =>
                    setGaps((items) =>
                      items.map((item, i) =>
                        i === index
                          ? {
                              ...item,
                              disposition: event.target
                                .value as typeof gap.disposition,
                            }
                          : item,
                      ),
                    )
                  }
                >
                  <option>blocking</option>
                  <option>unverified</option>
                </select>
              </label>
            </div>
            <label>
              Source revision
              <select
                required
                value={gap.source_revision_id}
                onChange={(event) =>
                  setGaps((items) =>
                    items.map((item, i) =>
                      i === index
                        ? { ...item, source_revision_id: event.target.value }
                        : item,
                    ),
                  )
                }
              >
                <option value="">Select exact revision</option>
                {draft.source_revision_ids.map((id) => (
                  <option key={id}>{id}</option>
                ))}
              </select>
            </label>
            <label>
              Rationale
              <input
                required
                maxLength={500}
                value={gap.rationale}
                onChange={(event) =>
                  setGaps((items) =>
                    items.map((item, i) =>
                      i === index
                        ? { ...item, rationale: event.target.value }
                        : item,
                    ),
                  )
                }
              />
            </label>
            <button
              className="button button-quiet"
              type="button"
              onClick={() =>
                setGaps((items) => items.filter((_, i) => i !== index))
              }
            >
              Remove gap
            </button>
          </fieldset>
        ))}
        <button
          className="button button-quiet"
          type="button"
          disabled={gaps.length >= 16 || !draft.source_revision_ids.length}
          onClick={() =>
            setGaps((items) => [
              ...items,
              {
                classification: "approval",
                disposition: "unverified",
                source_revision_id: "",
                rationale: "",
              },
            ])
          }
        >
          Add evidence-backed gap
        </button>
        <details>
          <summary>
            Exact source snapshot ({draft.source_revision_ids.length})
          </summary>
          <ul className="mono outline">
            {draft.source_revision_ids.map((id) => (
              <li key={id}>{id}</li>
            ))}
          </ul>
        </details>
        <details>
          <summary>Proposed rubric · {draft.proposed_rubric.title}</summary>
          <ol className="outline">
            {draft.proposed_rubric.questions.map((question) => (
              <li key={question.dimension}>
                <strong>{question.prompt}</strong>
                <p>
                  Expected answer: {question.choices[question.correct_choice]}
                </p>
                <p>{question.explanation}</p>
              </li>
            ))}
          </ol>
        </details>
        <label className="check">
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(event) => setConfirmed(event.target.checked)}
          />{" "}
          I confirm the exact source snapshot, current claim revisions and
          proposed rubric.
        </label>
        {error && (
          <div className="flow">
            <p role="alert" className="error">
              {error}
            </p>
            <button
              type="button"
              className="button button-quiet"
              onClick={reload}
            >
              Reload current draft
            </button>
          </div>
        )}
        <button
          className="button button-blue"
          disabled={!confirmed || !complete || busy}
        >
          {busy ? "Approving…" : "Approve immutable handover"}
          <ArrowRight size={16} />
        </button>
      </form>
    </section>
  );
}

function Correction({
  api,
  draft,
  claim,
  reload,
}: {
  api: Api;
  draft: Draft;
  claim: Schema["ClaimSummary"];
  reload: () => void;
}) {
  const tree = useResource<Schema["EvidenceTree"]>(
    api,
    `/claims/${claim.id}/tree?limit=100`,
  );
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <Load data={tree}>
      {(value) => {
        if (value.root.revision_id !== claim.revision_id)
          return (
            <p className="error">
              The claim revision changed. Reload the draft.
            </p>
          );
        return (
          <form
            className="flow correction"
            onSubmit={async (event) => {
              event.preventDefault();
              const fields = new FormData(event.currentTarget);
              const evidence = value.branches.flatMap(({ evidence }) =>
                evidence && evidence.relation !== "context"
                  ? [
                      {
                        revision_id: evidence.revision_id,
                        start: evidence.start,
                        end: evidence.end,
                        quote: evidence.excerpt,
                        relation: evidence.relation,
                      },
                    ]
                  : [],
              );
              const body = {
                draft_id: draft.id,
                expected_revision: draft.revision,
                reason: String(fields.get("reason")),
                content: {
                  kind: fields.get("kind") as Schema["ClaimContent"]["kind"],
                  status: fields.get(
                    "status",
                  ) as Schema["ClaimSummary"]["status"],
                  statement: String(fields.get("statement")),
                  evidence,
                },
              } satisfies Schema["ClaimPatch"];
              setBusy(true);
              setError("");
              try {
                await api<Schema["ClaimPatchView"]>(`/claims/${claim.id}`, {
                  method: "PATCH",
                  body,
                });
                reload();
              } catch (error) {
                setError(message(error));
              } finally {
                setBusy(false);
              }
            }}
          >
            <div className="form-columns">
              <label>
                Claim kind
                <select name="kind" defaultValue={claim.kind}>
                  {kinds.map((kind) => (
                    <option value={kind} key={kind}>
                      {label(kind)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Claim status
                <select name="status" defaultValue={claim.status}>
                  {statuses.map((status) => (
                    <option key={status}>{status}</option>
                  ))}
                </select>
              </label>
            </div>
            <label>
              Statement
              <textarea
                name="statement"
                required
                defaultValue={claim.statement}
                maxLength={4000}
              />
            </label>
            <label>
              Reason for correction
              <input name="reason" required maxLength={500} />
            </label>
            <p>
              Saving retains the visible citation spans and opens a new draft
              revision. Review confirmations must be entered again.
            </p>
            {error && (
              <p className="error" role="alert">
                {error}
              </p>
            )}
            <button className="button button-blue" disabled={busy}>
              Save correction
            </button>
          </form>
        );
      }}
    </Load>
  );
}
