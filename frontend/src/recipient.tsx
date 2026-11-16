"use client";

import { useRef, useState, type FormEvent } from "react";
import { ArrowRight, ClipboardCheck, FileCheck2 } from "lucide-react";
import { label, message, type Api, type Schema } from "./api";
import { Badge, Empty, Load, Pager, useResource } from "./data";
import { presentClaim, sourceRecordDetail } from "./handover-presentation";

export function Versions({
  api,
  projectId,
  versionId,
  recipient,
  openVersion,
  selectClaim,
  openRubric,
}: {
  api: Api;
  projectId: string;
  versionId: string;
  recipient: boolean;
  openVersion: (id: string) => void;
  selectClaim: (claim: string, version: string) => void;
  openRubric: (id: string) => void;
}) {
  const [offset, setOffset] = useState(0);
  const list = useResource<Schema["Page_VersionListItem_"]>(
    api,
    !versionId ? `/projects/${projectId}/versions?offset=${offset}` : "",
  );
  const version = useResource<Schema["VersionView"]>(
    api,
    versionId ? `/versions/${versionId}` : "",
  );
  return versionId ? (
    <div className="flow">
      <button className="back-button" onClick={() => openVersion("")}>
        ← Handover versions
      </button>
      <Load data={version}>
        {(value) => (
          <section className="panel flow">
            <div className="row spread">
              <h2>Approved handover</h2>
              <Badge value={value.status} />
            </div>
            {!value.handover ? (
              <Empty>The content of this handover is unavailable.</Empty>
            ) : value.handover.project_id !== projectId ? (
              <Empty>This version belongs to another project.</Empty>
            ) : (
              <>
                <div className="handover-reader-intro">
                  <div className="eyebrow"><FileCheck2 size={16} /> YOUR HANDOVER</div>
                  <h3>{value.handover.task}</h3>
                  <p>This handover is evidence-linked and was approved by a reviewer. Start with the sections below; open a source only when you need the original record.</p>
                </div>
                <small>
                  Version {value.handover.number} ·{" "}
                  {new Date(value.handover.approved_at).toLocaleString()}
                </small>
                {value.handover.unresolved.map((text) => (
                  <p className="notice" key={text}>
                    {text}
                  </p>
                ))}
                {value.handover.mode === "source_based" ? (
                  <div className="notice readiness-not-configured">
                    <strong>Readiness assessment not yet configured</strong>
                    <p>This source-based handover is ready to read and acknowledge. A reviewer can add a meaningful, evidence-grounded assessment when one is needed.</p>
                  </div>
                ) : <PackagePreview api={api} id={value.handover.rubric_id} />}
                <div className="row spread handover-section-heading">
                  <div><h3>What to know</h3><p className="muted">{value.handover.claims.length} evidence-backed sections</p></div>
                  <Badge value="human_reviewed" />
                </div>
                {value.handover.claims.map((claim) => (
                  <button
                    className="list-item handover-claim"
                    key={claim.id}
                    onClick={() => selectClaim(claim.id, value.id)}
                  >
                    <span>
                      <strong>{presentClaim(claim.statement)}</strong>
                      <small>
                        {label(claim.kind)} · {label(claim.status)}
                      </small>
                      <small className="claim-detail">{sourceRecordDetail(claim.statement)}</small>
                    </span>
                    <ArrowRight size={16} />
                  </button>
                ))}
                {value.handover.mode !== "source_based" && <button
                  className="button button-blue"
                  onClick={() => openRubric(value.handover!.rubric_id)}
                >
                  <ClipboardCheck size={17} /> Open Readiness Test
                </button>}
                {recipient && (
                  <Receipt
                    key={value.id}
                    api={api}
                    id={value.id}
                    current={value.status === "approved"}
                  />
                )}
              </>
            )}
          </section>
        )}
      </Load>
    </div>
  ) : (
    <section className="panel flow">
      <h2>Handover versions</h2>
      <Load data={list}>
        {(value) => (
          <>
            {!value.items.length && (
              <Empty>No approved handovers are visible for this project.</Empty>
            )}
            {value.items.map((item) => (
              <button
                className="list-item"
                key={item.id}
                onClick={() => openVersion(item.id)}
              >
                <span>
                  <strong>{item.task}</strong>
                  <small>
                    Version {item.number} ·{" "}
                    {new Date(item.approved_at).toLocaleDateString()}
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
  );
}

function PackagePreview({ api, id }: { api: Api; id: string }) {
  const data = useResource<Schema["Rehearsal"]>(api, `/rubrics/${id}`);
  return (
    <Load data={data}>
      {(value) => <PackageStatus value={value.package} />}
    </Load>
  );
}

function Receipt({
  api,
  id,
  current,
}: {
  api: Api;
  id: string;
  current: boolean;
}) {
  const data = useResource<Schema["ReceiptView"]>(
    api,
    `/versions/${id}/receipt`,
  );
  const [receipt, setReceipt] = useState<Schema["ReceiptView"]>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const value = receipt ?? data?.value;
  async function acknowledge() {
    setBusy(true);
    setError("");
    try {
      setReceipt(
        await api<Schema["ReceiptView"]>(`/versions/${id}/receipt`, {
          method: "POST",
        }),
      );
    } catch (error) {
      setError(message(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="receipt flow">
      <h3>
        <FileCheck2 size={17} /> Handover receipt
      </h3>
      {value?.acknowledged_at ? (
        <p>Acknowledged {new Date(value.acknowledged_at).toLocaleString()}.</p>
      ) : (
        current && (
          <button
            className="button button-quiet"
            disabled={busy}
            onClick={acknowledge}
          >
            Acknowledge handover
          </button>
        )
      )}
      {(error || (data?.status !== 404 && data?.error)) && (
        <p className="error" role="alert">
          {error || data?.error}
        </p>
      )}
    </div>
  );
}

function PackageStatus({ value }: { value: Schema["PackageReadiness"] }) {
  return (
    <div
      className={`package-status ${value.status === "ready" ? "" : "notice"}`}
    >
      <div className="row">
        <strong>Package readiness</strong>
        <Badge value={value.status} />
      </div>
      {!!value.gates.length && (
        <ul>
          {value.gates.map((gate) => (
            <li key={gate}>{label(gate)}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function Readiness({
  api,
  versionId,
  rubricId,
  attemptId,
  recipient,
  reviewer,
  openAttempt,
  back,
}: {
  api: Api;
  versionId: string;
  rubricId: string;
  attemptId: string;
  recipient: boolean;
  reviewer: boolean;
  openAttempt: (id: string) => void;
  back: () => void;
}) {
  const version = useResource<Schema["VersionView"]>(
    api,
    versionId && !rubricId && !attemptId ? `/versions/${versionId}` : "",
  );
  const resolvedVersionId = versionId || version?.value?.id || "";
  const resolvedRubricId = rubricId || version?.value?.handover?.rubric_id || "";
  const sourceBased = version?.value?.handover?.mode === "source_based";
  const rubric = useResource<Schema["Rehearsal"]>(
    api,
    resolvedRubricId && !attemptId ? `/rubrics/${resolvedRubricId}` : "",
  );
  const attempt = useResource<Schema["Assessment"]>(
    api,
    attemptId ? `/attempts/${attemptId}` : "",
  );
  if (!resolvedVersionId && !resolvedRubricId && !attemptId)
    return (
      <section className="panel flow">
        <h2>Readiness</h2>
        <Empty>Open a handover version to start its readiness rehearsal.</Empty>
        <button className="button button-quiet" onClick={back}>
          View handovers
        </button>
      </section>
    );
  return (
    <div className="flow">
      <button
        className="back-button"
        onClick={() => (attemptId && resolvedRubricId ? openAttempt("") : back())}
      >
        ←{" "}
        {attemptId && resolvedRubricId ? "Back to Readiness Test" : "Back to handover"}
      </button>
      {sourceBased && !attemptId && rubric?.value && !rubric.value.questions?.length ? (
        <section className="panel flow readiness-empty">
          <div className="eyebrow"><ClipboardCheck size={17} /> HANDOVER READINESS</div>
          <h2>Readiness assessment not configured</h2>
          <p>This source-based handover is available to read and acknowledge. A reviewer can add four evidence-grounded questions when the team needs a readiness check.</p>
          {rubric?.value?.generation_status === "needs_information" && <p className="notice">Missing dimensions: {(rubric.value.missing_dimensions ?? []).map(label).join(", ")}. Add those facts to the handover and approve a new version to regenerate the assessment.</p>}
          {reviewer ? <details><summary>Advanced manual override</summary><AssessmentConfigurator api={api} versionId={resolvedVersionId} onSaved={() => window.location.reload()} /></details> : <button className="button button-quiet" onClick={back}>Return to handover</button>}
        </section>
      ) : attemptId ? (
        <Load data={attempt}>
          {(value) => (
            <section className="panel flow">
              <div className="eyebrow">ASSESSMENT RESULT</div>
              <h2>Readiness result</h2>
              <PackageStatus value={value.package} />
              <div className="row">
                <strong>Recipient outcome</strong>
                <Badge value={value.status} />
              </div>
              <p className="score">
                <strong>{value.score ?? "—"}</strong>
                {value.score != null && "/100"} <small>Assessment score</small>
              </p>
              <div className="flow">
                {value.feedback?.map((item) => (
                  <div className="citation" key={item.dimension}>
                    <strong>
                      {label(item.dimension)} · {item.points}/{item.weight}
                    </strong>
                    <p>{item.explanation}</p>
                  </div>
                ))}
              </div>
              {value.review?.feedback && (
                <p className="notice">
                  Reviewer feedback: {value.review.feedback}
                </p>
              )}
              {value.advisory?.feedback && (
                <p>Advisory: {value.advisory.feedback}</p>
              )}
            </section>
          )}
        </Load>
      ) : (
        <Load data={rubric}>
          {(value) => (
            <Questionnaire
              key={value.id}
              {...{ api, rubric: value, recipient, openAttempt }}
            />
          )}
        </Load>
      )}
    </div>
  );
}

function AssessmentConfigurator({ api, versionId, onSaved }: { api: Api; versionId: string; onSaved: () => void }) {
  const version = useResource<Schema["VersionView"]>(api, versionId ? `/versions/${versionId}` : "");
  const revisionIds = version?.value?.handover?.source_revision_ids ?? [];
  const dimensions: Schema["Question"]["dimension"][] = ["action", "prerequisites", "evidence", "escalation"];
  const [title, setTitle] = useState("Project handover readiness");
  const [questions, setQuestions] = useState(() => dimensions.map((dimension) => ({ dimension, prompt: "", choices: ["", ""], correct_choice: 0, weight: 25, explanation: "", evidence_revision_ids: [] as string[] })));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  function update(index: number, key: string, value: string) {
    setQuestions((items) => items.map((item, i) => i === index ? { ...item, [key]: value } : item));
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError("");
    if (!revisionIds.length || questions.some((q) => !q.prompt.trim() || q.choices.some((choice) => !choice.trim()) || !q.explanation.trim())) {
      setError("Add a grounded question, two answer choices and an explanation for each readiness dimension."); return;
    }
    setBusy(true);
    try {
      await api(`/versions/${versionId}/readiness`, { method: "PUT", body: { title, threshold: 80, questions: questions.map((question) => ({ ...question, evidence_revision_ids: [revisionIds[0]] })) } });
      onSaved();
    } catch (err) { setError(message(err)); } finally { setBusy(false); }
  }
  return <form className="flow readiness-configurator" onSubmit={submit}>
    <label>Assessment title<input value={title} onChange={(event) => setTitle(event.target.value)} /></label>
    {questions.map((question, index) => <fieldset key={question.dimension} className="readiness-question-config">
      <legend>{label(question.dimension)}</legend>
      <label>Question<textarea value={question.prompt} onChange={(event) => update(index, "prompt", event.target.value)} placeholder={`What should the recipient know about ${label(question.dimension).toLowerCase()}?`} /></label>
      <div className="grid-2"><label>Choice 1<input value={question.choices[0]} onChange={(event) => setQuestions((items) => items.map((item, i) => i === index ? { ...item, choices: [event.target.value, item.choices[1]] } : item))} /></label><label>Choice 2<input value={question.choices[1]} onChange={(event) => setQuestions((items) => items.map((item, i) => i === index ? { ...item, choices: [item.choices[0], event.target.value] } : item))} /></label></div>
      <label>Explanation<textarea value={question.explanation} onChange={(event) => update(index, "explanation", event.target.value)} /></label>
    </fieldset>)}
    {error && <p className="error-text">{error}</p>}<button className="button button-primary" disabled={busy}>{busy ? "Saving assessment…" : "Save readiness assessment"}</button>
  </form>;
}

function Questionnaire({
  api,
  rubric,
  recipient,
  openAttempt,
}: {
  api: Api;
  rubric: Schema["Rehearsal"];
  recipient: boolean;
  openAttempt: (id: string) => void;
}) {
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [review, setReview] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const attempt = useRef<string>(undefined);
  const questions = rubric.questions ?? [];
  const count = questions.filter(
    (question) => answers[question.dimension] !== undefined,
  ).length;
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!review) {
      setReview(true);
      return;
    }
    setBusy(true);
    setError("");
    attempt.current ??= crypto.randomUUID();
    try {
      const body = {
        answers,
        client_attempt_id: attempt.current,
      } satisfies Schema["AttemptInput"];
      const result = await api<Schema["Assessment"]>(
        `/rubrics/${rubric.id}/attempts`,
        { method: "POST", body },
      );
      openAttempt(result.id);
    } catch (error) {
      setError(message(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel flow">
      <div className="eyebrow">
        <ClipboardCheck size={17} /> HANDOVER REHEARSAL
      </div>
      <h2>{rubric.title ?? "Readiness Test"}</h2>
      <PackageStatus value={rubric.package} />
      {!questions.length ? (
        <Empty>Questions are unavailable for this version.</Empty>
      ) : (
        <form className="flow" onSubmit={submit}>
          <p>
            {review
              ? "Review your answers before submitting."
              : `${count} of ${questions.length} questions answered`}
          </p>
          {questions.map((question, index) => (
            <fieldset key={question.dimension} className="gap-form">
              <legend>
                {index + 1}. {label(question.dimension)}
              </legend>
              <strong>{question.prompt}</strong>
              {review ? (
                <p>{question.choices[answers[question.dimension]]}</p>
              ) : (
                question.choices.map((choice, i) => (
                  <label key={i} className="check">
                    <input
                      type="radio"
                      name={question.dimension}
                      checked={answers[question.dimension] === i}
                      onChange={() => {
                        setAnswers((values) => ({
                          ...values,
                          [question.dimension]: i,
                        }));
                        attempt.current = undefined;
                      }}
                    />{" "}
                    {choice}
                  </label>
                ))
              )}
            </fieldset>
          ))}
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          {recipient ? (
            <div className="row">
              {review && (
                <button
                  type="button"
                  className="button button-quiet"
                  onClick={() => setReview(false)}
                >
                  Edit answers
                </button>
              )}
              <button
                className="button button-blue"
                disabled={busy || count !== questions.length}
              >
                {review ? "Submit assessment" : "Review answers"}
              </button>
            </div>
          ) : (
            <p className="empty">
              An assigned recipient can submit this rehearsal.
            </p>
          )}
        </form>
      )}
    </section>
  );
}
