"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, LockKeyhole } from "lucide-react";
import Link from "next/link";
import { Brand, Mark } from "../../src/brand";
import { createApi, message, type Schema } from "../../src/api";

export default function Login() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [email, setEmail] = useState("");
  const [visible, setVisible] = useState(false);
  const [registering, setRegistering] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const fields = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      const body = {
        email: String(fields.get("email")),
        password: String(fields.get("password")),
      } satisfies Schema["LoginInput"];
      if (registering) await createApi()("/auth/register", { method: "POST", body });
      await createApi()<Schema["SessionView"]>("/auth/login", {
        method: "POST",
        body,
      });
      router.replace("/app");
    } catch (error) {
      setError(message(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login">
      <section className="login-content">
        <header>
          <Brand />
          <Link className="text-link" href="/">
            <ArrowLeft size={16} /> Back home
          </Link>
        </header>
        <div className="login-form enter">
          <div className="eyebrow">
            <LockKeyhole size={15} /> KNOTDEVT WORKSPACE
          </div>
          <h1>
            Pick up <i>the thread.</i>
          </h1>
          <p>{registering ? "Create your account to start a workspace." : "Sign in to continue your workspace."}</p>
          <details>
            <summary>Explore Demo</summary>
            <p>Choose a preview, then use the sign-in details provided by your presenter.</p>
            <div className="row">
              {(["reviewer", "recipient", "restricted"] as const).map((role) => (
                <button key={role} type="button" className="button" onClick={() => setEmail(`${role}@knotdevt.test`)}>
                  {role === "reviewer" ? "Project Reviewer" : role === "recipient" ? "New Team Member" : "Limited Access Preview"}
                </button>
              ))}
            </div>
          </details>
          <form onSubmit={submit}>
            <label>
              Email
              <input
                name="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                type="email"
                placeholder="you@example.com"
                autoComplete="username"
                required
              />
            </label>
            <label>
              Password
              <input
                name="password"
                type={visible ? "text" : "password"}
                placeholder="Enter your password"
                autoComplete={registering ? "new-password" : "current-password"}
                minLength={registering ? 12 : 1}
                required
              />
            </label>
            <button type="button" className="text-link" aria-pressed={visible} onClick={() => setVisible(!visible)}>
              {visible ? "Hide password" : "Show password"}
            </button>
            {error && (
              <p role="alert" className="error">
                {error}
              </p>
            )}
            <button className="button button-blue" disabled={busy}>
              {busy ? "Please wait…" : registering ? "Create account" : "Sign in"} <ArrowRight size={18} />
            </button>
          </form>
          <button type="button" className="text-link" disabled={busy} onClick={() => { setRegistering(!registering); setError(""); }}>
            {registering ? "Already have an account? Sign in" : "Create account"}
          </button>
        </div>
        <small>KnotDevt · K0.1.0</small>
      </section>
      <aside className="login-art">
        <div className="eyebrow">
          <Mark /> THE THREAD CONTINUES
        </div>
        <svg viewBox="0 0 400 400" aria-hidden="true">
          <path
            pathLength="1"
            className="hero-thread"
            d="M-20 294C60 294 111 90 198 90s126 204 222 204M-20 110c80 0 131 204 218 204S324 110 420 110"
            fill="none"
            stroke="currentColor"
            strokeWidth="18"
            strokeLinecap="round"
          />
        </svg>
        <div>
          Good work deserves
          <br />
          <i>good continuity.</i>
        </div>
      </aside>
    </main>
  );
}
