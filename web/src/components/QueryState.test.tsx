import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "../lib/api";
import { errorText, QueryError, QueryState } from "./QueryState";

const base = { isLoading: false, error: null, refetch: vi.fn() };

describe("QueryState", () => {
  it("shows loading", () => {
    render(<QueryState q={{ ...base, isLoading: true }}>x</QueryState>);
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });
  it("shows error and Retry refetches", async () => {
    const refetch = vi.fn();
    render(<QueryState q={{ ...base, error: new ApiError("down", 503), refetch }} label="Sets">x</QueryState>);
    expect(screen.getByRole("alert")).toHaveTextContent("Sets: down (503)");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(refetch).toHaveBeenCalledOnce();
  });
  it("shows empty text", () => {
    render(<QueryState q={{ ...base, data: [] }} empty="Nothing" isEmpty={(d: number[]) => d.length === 0}>x</QueryState>);
    expect(screen.getByText("Nothing")).toBeInTheDocument();
  });
  it("renders children with data", () => {
    render(<QueryState q={{ ...base, data: [1, 2] }}>{(d: number[]) => <b>{d.length} items</b>}</QueryState>);
    expect(screen.getByText("2 items")).toBeInTheDocument();
  });
  it("keeps stale data visible when a refetch fails", () => {
    render(<QueryState q={{ ...base, data: [1], error: new Error("x") }}>{() => <b>stale</b>}</QueryState>);
    expect(screen.getByText("stale")).toBeInTheDocument();
  });
});

describe("errorText / QueryError", () => {
  it("maps fetch TypeError to a friendly message", () => {
    expect(errorText(new TypeError("Failed to fetch"))).toMatch(/Cannot reach the API/);
  });
  it("QueryError renders nothing without error", () => {
    const { container } = render(<QueryError q={{ error: null, refetch: vi.fn() }} />);
    expect(container).toBeEmptyDOMElement();
  });
});
