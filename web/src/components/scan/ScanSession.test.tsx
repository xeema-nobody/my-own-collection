import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { mockApi, renderPage } from "../../test/utils";
import ScanSession from "./ScanSession";

const EV = { id: "e1", at: "", kind: "add", card_id: "pokemon:base1-4", label: "Charizard, Base", quantity_added: 1, quantity_after: 1, type_conflict: false, condition: "NM", language: "en", session_id: "s1" };

describe("ScanSession (laptop)", () => {
  it("hidden until phone mode is set up", () => {
    mockApi({ "GET /api/scan/status": { enabled: false, url: null, login: null } });
    renderPage(<ScanSession />);
    expect(screen.queryByRole("button", { name: /Scan raw cards/ })).toBeNull();
  });

  it("starts a session and shows what the phone adds", async () => {
    mockApi({
      "GET /api/scan/status": { enabled: true, url: "https://x/scan", login: "me" },
      "POST /api/scan/sessions": { id: "s1", created_at: "", mode: "raw" },
      "GET /api/scan/events": { events: [EV], latest: "e1" },
      "GET /api/cards/pokemon%3Abase1-4": { images: { small: "https://img/4.png" } },
    });
    renderPage(<ScanSession />);
    await userEvent.click(await screen.findByRole("button", { name: /Scan raw cards/ }));
    expect(await screen.findByText("Charizard, Base", {}, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.getByText(/Raw session: 1 added this session/)).toBeInTheDocument();
  });

  it.each([["Scan raw cards", "raw", "Raw session"], ["Scan slabs", "slab", "Slab session"]])("%s starts a %s session", async (label, mode, header) => {
    const api = mockApi({
      "GET /api/scan/status": { enabled: true, url: "https://x/scan", login: "me" },
      "POST /api/scan/sessions": (init?: RequestInit) => ({ id: "s1", created_at: "", mode: JSON.parse(String(init?.body)).mode }),
      "GET /api/scan/events": { events: [], latest: null },
    });
    renderPage(<ScanSession />);
    await userEvent.click(await screen.findByRole("button", { name: label }));
    expect(await screen.findByText(new RegExp(`${header}:`))).toBeInTheDocument();
    const post = api.mock.calls.find(([u]) => String(u).endsWith("/api/scan/sessions"))!;
    expect(JSON.parse((post[1] as RequestInit).body as string)).toEqual({ mode });
  });
});
