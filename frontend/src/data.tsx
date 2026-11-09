"use client";

import { useEffect, useState, type ReactNode } from "react";
import { ApiError, label, message, type Api } from "./api";

export type Resource<T> = {
  path: string;
  value?: T;
  error?: string;
  status?: number;
};
export type Page<T> = { items: T[]; next_offset: number | null };

export function useResource<T>(api: Api, path: string, refresh = 0) {
  const [result, setResult] = useState<Resource<T>>();
  const key = `${path}#${refresh}`;
  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    api<T>(path, { signal: controller.signal }).then(
      (value) => setResult({ path: key, value }),
      (error) => {
        if (!controller.signal.aborted)
          setResult({
            path: key,
            error: message(error),
            status: error instanceof ApiError ? error.status : undefined,
          });
      },
    );
    return () => controller.abort();
  }, [api, key, path]);
  return result?.path === key ? result : undefined;
}

export function Load<T>({
  data,
  children,
}: {
  data: Resource<T> | undefined;
  children: (value: T) => ReactNode;
}) {
  if (!data)
    return (
      <div className="skeleton" role="status">
        Loading…
      </div>
    );
  if (data.error)
    return (
      <p className="error" role="alert">
        {data.error}
      </p>
    );
  return data.value === undefined ? null : children(data.value);
}

export function Badge({ value }: { value: string }) {
  const tone = /blocked|failed|unavailable|contradict|withdrawn/.test(value)
    ? "danger"
    : /stale|review|pending|unverified|unresolved|open/.test(value)
      ? "warning"
      : /approved|ready|succeeded|completed|resolved/.test(value)
        ? "success"
        : "neutral";
  return <span className={`badge ${tone}`}>{label(value)}</span>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="empty">{children}</p>;
}

export function Pager({
  offset,
  next,
  onChange,
}: {
  offset: number;
  next: number | null;
  onChange: (offset: number) => void;
}) {
  return offset || next !== null ? (
    <div className="row pager">
      <button
        className="button button-quiet"
        disabled={!offset}
        onClick={() => onChange(Math.max(0, offset - 25))}
      >
        Previous
      </button>
      <button
        className="button button-quiet"
        disabled={next === null}
        onClick={() => next !== null && onChange(next)}
      >
        Next
      </button>
    </div>
  ) : null;
}
