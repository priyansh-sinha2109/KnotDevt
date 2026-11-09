"use client";

import { useRef, useState, type FormEvent } from "react";
import { ArrowRight, ClipboardCheck, FileCheck2 } from "lucide-react";
import { label, message, type Api, type Schema } from "./api";
import { Badge, Empty, Load, Pager, useResource } from "./data";

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
                <h3>{value.handover.task}</h3>
                <small>
                  Version {value.handover.number} ·{" "}
                  {new Date(value.handover.approved_at).toLocaleString()}
                </small>
                {value.handover.unresolved.map((text) => (
                  <p className="notice" key={text}>
                    {text}
                  </p>
                ))}
                <PackagePreview api={api} id={value.handover.rubric_id} />
                <h3>Handover claims</h3>
                {value.handover.claims.map((claim) => (
                  <button
                    className="list-item"
                    key={claim.id}
                    onClick={() => selectClaim(claim.id, value.id)}
                  >
                    <span>
                      <strong>{claim.statement}</strong>
                      <small>
                        {label(claim.kind)} · {label(claim.status)}
                      </small>
                    </span>
                    <ArrowRight size={16} />
                  </button>
                ))}
                <button
                  className="button button-blue"
                  onClick={() => openRubric(value.handover!.rubric_id)}
                >
                  <ClipboardCheck size={17} /> Open Readiness Test
                </button>
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
  rubricId,
  attemptId,
  recipient,
  openAttempt,
  back,
}: {
  api: Api;
  rubricId: string;
  attemptId: string;
  recipient: boolean;
  openAttempt: (id: string) => void;
  back: () => void;
}) {
  const rubric = useResource<Schema["Rehearsal"]>(
    api,
    rubricId && !attemptId ? `/rubrics/${rubricId}` : "",
  );
  const attempt = useResource<Schema["Assessment"]>(
    api,
    attemptId ? `/attempts/${attemptId}` : "",
  );
  if (!rubricId && !attemptId)
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
        onClick={() => (attemptId && rubricId ? openAttempt("") : back())}
      >
        ←{" "}
        {attemptId && rubricId ? "Back to Readiness Test" : "Back to handover"}
      </button>
      {attemptId ? (
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
