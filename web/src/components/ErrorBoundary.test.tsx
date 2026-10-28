import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import ErrorBoundary from "./ErrorBoundary";

const Boom = () => { throw new Error("kaboom"); };

describe("ErrorBoundary", () => {
  it("catches a throwing child", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(<ErrorBoundary><Boom /></ErrorBoundary>);
    expect(screen.getByRole("alert")).toHaveTextContent("kaboom");
    expect(screen.getByRole("button", { name: "Reload" })).toBeInTheDocument();
  });
  it("renders children when fine", () => {
    render(<ErrorBoundary><p>ok</p></ErrorBoundary>);
    expect(screen.getByText("ok")).toBeInTheDocument();
  });
});
