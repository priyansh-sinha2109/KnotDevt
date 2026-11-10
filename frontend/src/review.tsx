"use client";

import { useRef, useState } from "react";
import { ArrowRight, ShieldCheck, TriangleAlert } from "lucide-react";
import { evidenceTitle, label, message, type Api, type Schema } from "./api";
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

function snapshotLabel(draft: Draft, revision: string, index: number) {
  const source = draft.source_snapshot?.find((item) => item.revision_id === revision);
  if (!source) return `Evidence ${index + 1}`;
  const title = evidenceTitle(source.source_id, source.excerpt);
  return `${title} · ${new Date(source.event_time).toLocaleDateString()}`;
}

export function Drafts({
  api,
  projectId,
  draftId,
  openDraft,
  selectClaim,
  exploreClaim,
  onCorrection,
  publish,
}: {
  api: Api;
  projectId: string;
  draftId: string;
  openDraft: (id: string) => void;
  selectClaim: (id: string) => void;
  exploreClaim: (id: string) => void;
  onCorrection: () => void;
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
              {...{ api, draft: value, selectClaim, exploreClaim, publish }}
              reload={() => {
                selectClaim("");
                onCorrection();
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
  exploreClaim,
  publish,
  reload,
}: {
  api: Api;
  draft: Draft;
  selectClaim: (id: string) => void;
  exploreClaim: (id: string) => void;
  publish: (id: string) => void;
  reload: () => void;
}) {
  const [decisions, setDecisions] = useState<Record<string, Partial<Gap>>>({});
  const [gaps, setGaps] = useState<Schema["AdditionalGap"][]>([]);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [correction, setCorrection] = useState("");
  const confirmation = useRef<HTMLDialogElement>(null);
  const reviewedCount = draft.claims.filter(({ claim }) => {
    const decision = decisions[claim.revision_id];
    return decision?.classification && decision.disposition && decision.rationale?.trim();
  }).length;
  const dispositions = [...Object.values(decisions), ...gaps];
  const gapSummary = ["blocking", "unverified", "resolved"].map((value) => `${dispositions.filter((item) => item.disposition === value).length} ${value}`).join(" · ");
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

  async function approve() {
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
              <button className="button button-quiet" onClick={() => exploreClaim(claim.id)}>Explore Evidence</button>
              <button
                className="button button-quiet"
                id={`correct-${claim.id}`}
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
      <form
        className="panel flow"
        onSubmit={(event) => {
          event.preventDefault();
          if (confirmed && complete && !busy) confirmation.current?.showModal();
        }}
      >
        <h2>Critical-gap review</h2>
        <p role="status">Reviewed {reviewedCount} of {draft.claims.length} claims</p>
        <p>{gapSummary}</p>
        <p>
          Classify what each claim means for this task. Mark a gap blocking when it prevents the task, unverified when the evidence is incomplete, or resolved only when the evidence shows it is closed.
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
              <p>{flags.some((flag) => citationFlags.includes(flag)) ? "Citation needs correction" : "Review whether the source supports the full claim"}</p>
              <button type="button" className="button button-quiet" onClick={() => exploreClaim(claim.id)}>Explore Evidence</button>
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
                        disposition: undefined,
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
              Supporting evidence
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
                <option value="">Choose evidence</option>
                {draft.source_revision_ids.map((id, index) => (
                  <option key={id} value={id}>{snapshotLabel(draft, id, index)}</option>
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
            {draft.source_revision_ids.map((id, index) => (
              <li key={id}>{snapshotLabel(draft, id, index)}</li>
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
          proposed rubric. I reviewed whether each cited excerpt supports its claim.
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
      <dialog
        ref={confirmation}
        className="panel approval-dialog"
        aria-labelledby="approval-confirmation-title"
      >
        <div className="flow">
          <h2 id="approval-confirmation-title">Publish this handover?</h2>
          <p>{reviewedCount} claims reviewed · {gapSummary}</p>
          <p>
            Draft revision {draft.revision} and its reviewed source snapshot
            will be published as an immutable version for the assigned
            recipients.
          </p>
          <div className="row">
            <button
              type="button"
              className="button button-quiet"
              onClick={() => confirmation.current?.close()}
            >
              Cancel
            </button>
            <button
              type="button"
              className="button button-blue"
              onClick={() => {
                confirmation.current?.close();
                void approve();
              }}
            >
              Publish version
            </button>
          </div>
        </div>
      </dialog>
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
  const [addCitation, setAddCitation] = useState(false);
  const [citationSource, setCitationSource] = useState("");
  const citationPreview = draft.source_snapshot?.find((item) => item.revision_id === citationSource);
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
              const evidence: Schema["EvidencePointer"][] =
                value.branches.flatMap(({ evidence }, index) =>
                  evidence &&
                  evidence.relation !== "context" &&
                  fields.has(`keep-citation-${index}`)
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
              if (addCitation) {
                const revision = String(fields.get("citation-revision"));
                const quote = String(fields.get("citation-quote"));
                const manualStart = String(fields.get("citation-start") ?? "");
                const excerpt = citationPreview?.excerpt ?? "";
                const index = excerpt.indexOf(quote);
                const unique = index >= 0 && index === excerpt.lastIndexOf(quote);
                const start = manualStart ? Number(manualStart) : unique ? Array.from(excerpt.slice(0, index)).length : -1;
                const end = start + Array.from(quote).length;
                if (
                  !draft.source_revision_ids.includes(revision) ||
                  !Number.isInteger(start) ||
                  start < 0 ||
                  !quote ||
                  end > 12000
                ) {
                  setError(
                    "Choose evidence and enter an exact quote. Use a longer quote if the text appears more than once.",
                  );
                  return;
                }
                evidence.push({
                  revision_id: revision,
                  start,
                  end,
                  quote,
                  relation: "supports",
                });
              }
              const status = fields.get(
                "status",
              ) as Schema["ClaimSummary"]["status"];
              if (
                status === "resolved" &&
                (!evidence.some(
                  (citation) => citation.relation === "supports",
                ) ||
                  evidence.some(
                    (citation) => citation.relation === "contradicts",
                  ))
              ) {
                setError(
                  "A resolved claim needs supporting evidence and cannot retain a contradictory citation.",
                );
                return;
              }
              if (evidence.length > 24) {
                setError("A claim can retain at most 24 citations.");
                return;
              }
              const body = {
                draft_id: draft.id,
                expected_revision: draft.revision,
                reason: String(fields.get("reason")),
                content: {
                  kind: fields.get("kind") as Schema["ClaimContent"]["kind"],
                  status,
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
            <fieldset className="gap-form">
              <legend>Citation spans to retain</legend>
              {value.branches.map(
                ({ evidence }, index) =>
                  evidence &&
                  evidence.relation !== "context" && (
                    <label className="check" key={index}>
                      <input
                        type="checkbox"
                        name={`keep-citation-${index}`}
                        defaultChecked
                      />
                      <span>
                        {evidence.original_id} · {label(evidence.relation)} ·{" "}
                        {evidence.excerpt}
                      </span>
                    </label>
                  ),
              )}
              <label className="check">
                <input
                  type="checkbox"
                  checked={addCitation}
                  onChange={(event) => setAddCitation(event.target.checked)}
                />
                Add supporting citation from the draft snapshot
              </label>
              {addCitation && (
                <>
                  <label>
                    Supporting evidence
                    <select name="citation-revision" required value={citationSource} onChange={(event) => setCitationSource(event.target.value)}>
                      <option value="">Choose evidence</option>
                      {draft.source_revision_ids.map((id, index) => (
                        <option key={id} value={id}>{snapshotLabel(draft, id, index)}</option>
                      ))}
                    </select>
                  </label>
                  {citationPreview && <blockquote className="source-text">{citationPreview.excerpt}</blockquote>}
                  <details>
                    <summary>Specify a quote position</summary>
                    <label>Quote start offset <input name="citation-start" type="number" min={0} max={11999} step={1} /></label>
                  </details>
                  <label>
                    Exact supporting quote
                    <textarea
                      name="citation-quote"
                      maxLength={12000}
                      required
                    />
                  </label>
                  <small>
                    Use the zero-based character offset in the source. The
                    backend verifies the exact quote and snapshot.
                  </small>
                </>
              )}
            </fieldset>
            <p>
              Saving creates a new draft revision. Review confirmations must be
              entered again.
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
