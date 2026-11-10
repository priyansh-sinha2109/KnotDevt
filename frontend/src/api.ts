import type { components } from "./api-schema";

export type Schema = components["schemas"];
const endpoint = (
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8080/api/v1"
).replace(/\/+$/, "");

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export type Api = <T>(
  path: string,
  options?: {
    method?: "POST" | "PATCH";
    body?: unknown;
    key?: string;
    signal?: AbortSignal;
  },
) => Promise<T>;

export function createApi(csrf?: string, expired?: () => void): Api {
  return async (path, { method, body, key, signal } = {}) => {
    const headers = new Headers();
    if (body !== undefined) headers.set("Content-Type", "application/json");
    if (method && csrf) headers.set("X-CSRF-Token", csrf);
    if (key) headers.set("Idempotency-Key", key);
    const response = await fetch(endpoint + path, {
      method,
      credentials: "include",
      headers,
      signal,
      cache: "no-store",
      body: body === undefined ? undefined : JSON.stringify(body),
    }).catch((error: unknown) => {
      if (signal?.aborted) throw error;
      throw new Error("Cannot reach the KnotDevt API. Check your connection and try again.");
    });
    if (!response.ok) {
      if (response.status === 401) expired?.();
      const error = await response.json().catch(() => null);
      const message =
        error?.message ??
        (Array.isArray(error?.detail)
          ? error.detail
              .map(
                (item: { loc: string[]; msg: string }) =>
                  `${item.loc.join(".")}: ${item.msg}`,
              )
              .join("; ")
          : error?.detail);
      throw new ApiError(
        response.status,
        typeof message === "string"
          ? message
          : `Request failed (HTTP ${response.status}).`,
      );
    }
    return response.status === 204 ? undefined : response.json();
  };
}

export function label(value: string) {
  return value.replaceAll("_", " ").replaceAll("-", " ");
}

export function evidenceTitle(reference: string, excerpt: string) {
  if (!/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(reference))
    return reference;
  const text = excerpt.trim().replace(/\s+/g, " ");
  return text.length > 72 ? `${text.slice(0, 71)}…` : text || "Project evidence";
}

export function message(error: unknown) {
  return error instanceof Error
    ? error.message
    : "An unexpected error occurred.";
}
