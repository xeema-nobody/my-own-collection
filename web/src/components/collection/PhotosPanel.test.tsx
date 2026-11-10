import { afterEach, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { mockApi, renderPage } from "../../test/utils";
import PhotosPanel from "./PhotosPanel";

afterEach(() => vi.restoreAllMocks());
const P = (id: string, o: object = {}) => ({ id, stack_id: "s1", kind: "front", cover: false, order: 0, w: 100, h: 140, bytes: 1000, created_at: "2026-11-11", ...o });

it("shows photos with the cover marked, and an empty hint", async () => {
  mockApi({ "GET /api/collection/s1/photos": [P("a", { cover: true }), P("b", { kind: "back", order: 1 })] });
  renderPage(<PhotosPanel id="s1" />);
  expect(await screen.findByText("Cover")).toBeInTheDocument();
  expect(screen.getAllByRole("img")).toHaveLength(2);
  expect(screen.getByRole("heading", { name: "Photos (2)" })).toBeInTheDocument();
});

it("uploads chosen files with the kind, makes cover, deletes", async () => {
  let list = [P("a", { cover: true }), P("b", { order: 1 })];
  const api = mockApi({
    "GET /api/collection/s1/photos": () => list,
    "POST /api/collection/s1/photos": () => P("c"),
    "PATCH /api/photos/b": () => P("b", { cover: true }),
    "DELETE /api/photos/a": { status: 204 },
  });
  const user = userEvent.setup();
  renderPage(<PhotosPanel id="s1" />);
  await screen.findByText("Cover");
  await user.upload(screen.getByLabelText("Choose photos"), new File(["x"], "n.jpg", { type: "image/jpeg" }));
  await waitFor(() => expect(api.mock.calls.some(([u, i]) => String(u).includes("/photos?kind=front") && (i as RequestInit).method === "POST")).toBe(true));
  await user.click(screen.getAllByRole("button", { name: "Make cover" })[1]);
  await waitFor(() => expect(api.mock.calls.some(([u, i]) => String(u).endsWith("/api/photos/b") && JSON.parse((i as RequestInit).body as string).cover === true)).toBe(true));
  await user.click(screen.getAllByRole("button", { name: "Delete photo" })[0]);
  await waitFor(() => expect(api.mock.calls.some(([u, i]) => String(u).endsWith("/api/photos/a") && (i as RequestInit).method === "DELETE")).toBe(true));
});

it("slab stacks default the kind to slab front", async () => {
  mockApi({ "GET /api/collection/s1/photos": [] });
  renderPage(<PhotosPanel id="s1" graded />);
  expect(await screen.findByText(/No photos yet/)).toBeInTheDocument();
  expect(screen.getByRole("combobox", { name: "Photo kind" })).toHaveTextContent("Slab front");
});
