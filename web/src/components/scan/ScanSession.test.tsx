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
    expect(screen.queryByRole("button", { name: /Start a scan/ })).toBeNull();
  });

  it("starts a session and shows what the phone adds", async () => {
    mockApi({
      "GET /api/scan/status": { enabled: true, url: "https://x/scan", login: "me" },
      "POST /api/scan/sessions": { id: "s1", created_at: "" },
      "GET /api/scan/events": { events: [EV], latest: "e1" },
      "GET /api/cards/pokemon%3Abase1-4": { images: { small: "https://img/4.png" } },
    });
    renderPage(<ScanSession />);
    await userEvent.click(await screen.findByRole("button", { name: /Start a scan/ }));
    expect(await screen.findByText("Charizard, Base", {}, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.getByText(/1 added this session/)).toBeInTheDocument();
  });
});
