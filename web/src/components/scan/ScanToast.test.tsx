import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { mockApi, renderPage } from "../../test/utils";
import ScanToast from "./ScanToast";
import PhoneLink from "./PhoneLink";

describe("ScanToast", () => {
  it("stays silent and does not poll while phone mode is off", async () => {
    const api = mockApi({ "/api/scan/status": { enabled: false, url: null, login: null } });
    renderPage(<ScanToast />);
    await new Promise((r) => setTimeout(r, 50));
    expect(api.mock.calls.some(([u]) => String(u).includes("/api/scan/events"))).toBe(false);
  });

  it("takes a cursor first, then announces new phone adds", async () => {
    const seen: string[] = [];
    mockApi({
      "/api/scan/status": { enabled: true, url: "https://m.ts.net/scan", login: "me@x" },
      "/api/scan/events": () => { seen.push("poll"); return seen.length === 1 ? { events: [], latest: null }
        : { events: [{ id: "a1", at: "", card_id: "c", label: "Charizard, Base", quantity_added: 1, quantity_after: 2, type_conflict: false }], latest: "a1" }; },
    });
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderPage(<ScanToast />);
    await vi.advanceTimersByTimeAsync(4500);
    expect(await screen.findByRole("status")).toHaveTextContent(/Added: Charizard, Base \(now 2\)/);
    vi.useRealTimers();
  });
});

describe("PhoneLink", () => {
  it("explains the one-time setup when not configured", async () => {
    mockApi({ "/api/scan/status": { enabled: false, url: null, login: null } });
    renderPage(<PhoneLink />);
    expect(await screen.findByText(/not set up yet/)).toBeInTheDocument();
    expect(screen.getByText(/MagicDNS/)).toBeInTheDocument();
  });
  it("shows the QR and link when configured", async () => {
    mockApi({ "/api/scan/status": { enabled: true, url: "https://m.ts.net/scan", login: "me@x" } });
    renderPage(<PhoneLink />);
    expect(await screen.findByText("https://m.ts.net/scan")).toBeInTheDocument();
    expect(await screen.findByAltText(/QR code for https:\/\/m.ts.net\/scan/)).toHaveAttribute("src", expect.stringMatching(/^data:image\/png/));
  });
});
