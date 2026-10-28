import type { ReactNode } from "react";
import { ApiError } from "../lib/api";

type Q<T> = { data?: T; isLoading: boolean; error: unknown; refetch: () => unknown };

/** Human text for any thrown value; unwraps `ApiError` / `Error`. */
export function errorText(e: unknown): string {
  if (e instanceof ApiError) return e.status ? `${e.message} (${e.status})` : e.message;
  if (e instanceof TypeError) return "Cannot reach the API. Is the backend running?";
  return e instanceof Error ? e.message : String(e);
}

/** Error box with a Retry button; renders nothing while `q` has no error. */
export function QueryError({ q, label }: { q: Pick<Q<unknown>, "error" | "refetch">; label?: string }) {
  if (!q.error) return null;
  return (
    <div role="alert" className="flex items-center gap-3 rounded border border-red-300 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300">
      <span>{label ? `${label}: ` : ""}{errorText(q.error)}</span>
      <button className="btn-ghost ml-auto" onClick={() => q.refetch()}>Retry</button>
    </div>
  );
}

/** Loading text, error + Retry, empty text, or children (called with the data when it is a function). */
export function QueryState<T>({ q, label, empty, isEmpty, children }: {
  q: Q<T>; label?: string; empty?: string; isEmpty?: (d: T) => boolean; children: ReactNode | ((d: T) => ReactNode);
}) {
  if (q.error && q.data === undefined) return <QueryError q={q} label={label} />;
  if (q.isLoading || q.data === undefined) return <p className="opacity-70">Loading…</p>;
  if (empty && (isEmpty ? isEmpty(q.data) : false)) return <p className="opacity-70">{empty}</p>;
  return <>{typeof children === "function" ? children(q.data) : children}</>;
}
