import type { ReactElement } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { render } from "@testing-library/react";
import { vi } from "vitest";

export function renderPage(ui: ReactElement, route = "/") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter></QueryClientProvider>);
}

type Reply = unknown | ((init?: RequestInit) => unknown);
/** Mock `fetch`: routes keyed by "METHOD /path-prefix" or "/path-prefix"; value is JSON, `{status, body}` or a function. */
export function mockApi(routes: Record<string, Reply | { status: number; body?: unknown }>) {
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    const method = init?.method ?? "GET";
    const key = Object.keys(routes).sort((a, b) => b.length - a.length)
      .find((k) => { const [m, p] = k.includes(" ") ? k.split(" ") : ["GET", k]; return m === method && url.pathname.startsWith(p); });
    if (!key) return new Response(JSON.stringify({ detail: `unmocked ${method} ${url.pathname}` }), { status: 599 });
    let r: any = routes[key];
    if (typeof r === "function") r = r(init);
    const isErr = r && typeof r === "object" && "status" in r && typeof r.status === "number";
    return new Response(isErr && r.status === 204 ? null : JSON.stringify(isErr ? r.body ?? {} : r), { status: isErr ? r.status : 200 });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}
