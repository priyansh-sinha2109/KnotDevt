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
          <p>Sign in with your existing KnotDevt account.</p>
          <form onSubmit={submit}>
            <label>
              Email
              <input
                name="email"
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
                type="password"
                placeholder="Enter your password"
                autoComplete="current-password"
                required
              />
            </label>
            {error && (
              <p role="alert" className="error">
                {error}
              </p>
            )}
            <button className="button button-blue" disabled={busy}>
              {busy ? "Signing in…" : "Sign in"} <ArrowRight size={18} />
            </button>
          </form>
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
