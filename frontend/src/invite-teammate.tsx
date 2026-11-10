"use client";

import { useRef, useState, type FormEvent } from "react";
import { UserPlus } from "lucide-react";
import { message, type Api, type Schema } from "./api";

export function InviteTeammate({ api, project }: { api: Api; project: Schema["ProjectView"] }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const codeField = useRef<HTMLInputElement>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [copyStatus, setCopyStatus] = useState("");

  async function createInvitation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || code) return;
    const email = String(new FormData(event.currentTarget).get("email") ?? "").trim();
    setBusy(true);
    setError("");
    try {
      const invitation = await api<Schema["InviteView"]>(`/projects/${project.id}/invitations`, {
        method: "POST",
        body: { email },
      });
      setCode(invitation.code);
    } catch (error) {
      setError(message(error));
    } finally {
      setBusy(false);
    }
  }

  async function copyInvitation() {
    try {
      await navigator.clipboard.writeText(code);
      setCopyStatus("Invitation copied. Share it privately with your teammate.");
    } catch {
      codeField.current?.focus();
      codeField.current?.select();
      setCopyStatus("Copy the selected code using your device’s copy command.");
    }
  }

  return (
    <>
      <button className="button" onClick={() => dialog.current?.showModal()}>
        <UserPlus size={16} aria-hidden="true" /> Invite teammate
      </button>
      <dialog
        ref={dialog}
        className="panel approval-dialog"
        aria-labelledby="invite-teammate-title"
        onCancel={(event) => { if (busy) event.preventDefault(); }}
        onClose={() => { setCode(""); setError(""); setCopyStatus(""); }}
      >
        <div className="flow">
          <h2 id="invite-teammate-title">Invite teammate</h2>
          <p>Invite a teammate to receive handovers in {project.name}.</p>
          {code ? (
            <div className="flow">
              <label>
                Invitation code
                <input ref={codeField} value={code} readOnly onFocus={(event) => event.currentTarget.select()} />
              </label>
              <p>Share this code privately. It expires in one hour and can be used once by the invited account.</p>
              <button className="button button-blue" onClick={copyInvitation}>Copy invitation</button>
              {copyStatus && <p role="status">{copyStatus}</p>}
            </div>
          ) : (
            <form className="flow" onSubmit={createInvitation}>
              <label>Teammate email <input type="email" name="email" autoComplete="off" required maxLength={254} /></label>
              <div>
                <label htmlFor="invite-teammate-role">Role</label>
                <select id="invite-teammate-role" name="role" defaultValue="recipient">
                  <option value="recipient">Recipient</option>
                </select>
              </div>
              {error && <p role="alert" className="error">{error}</p>}
              <button className="button button-blue" disabled={busy}>{busy ? "Creating…" : "Create invitation"}</button>
            </form>
          )}
          <button className="button button-quiet" disabled={busy} onClick={() => dialog.current?.close()}>Close</button>
        </div>
      </dialog>
    </>
  );
}
