import { describe, expect, it, vi } from "vitest";
import { render, renderHook, act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Section, SegmentedControl, Badge, Kpi, EmptyState } from "./index";
import ThemeToggle from "../ThemeToggle";
import { useTheme } from "../../lib/theme";

describe("Section", () => {
  it("collapses and remembers state", async () => {
    localStorage.clear();
    const { unmount } = render(<Section title="Prices" collapsible id="t1"><p>body</p></Section>);
    expect(screen.getByText("body")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /toggle prices/i }));
    expect(screen.queryByText("body")).not.toBeInTheDocument();
    unmount();
    render(<Section title="Prices" collapsible id="t1"><p>body</p></Section>);
    expect(screen.queryByText("body")).not.toBeInTheDocument();
  });
  it("non-collapsible always shows body", () => {
    render(<Section title="X"><p>body</p></Section>);
    expect(screen.getByText("body")).toBeInTheDocument();
  });
});

describe("SegmentedControl", () => {
  it("reports the clicked option", async () => {
    const on = vi.fn();
    render(<SegmentedControl label="Range" value="a" onChange={on} options={[{ value: "a", label: "A" }, { value: "b", label: "B" }]} />);
    expect(screen.getByRole("radio", { name: "A" })).toHaveAttribute("aria-checked", "true");
    await userEvent.click(screen.getByRole("radio", { name: "B" }));
    expect(on).toHaveBeenCalledWith("b");
  });
});

describe("theme", () => {
  it("toggle sets class and persists each choice", async () => {
    localStorage.clear();
    render(<ThemeToggle />);
    await userEvent.click(screen.getByRole("radio", { name: "Dark" }));
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(localStorage.getItem("moc-theme")).toBe("dark");
    await userEvent.click(screen.getByRole("radio", { name: "Light" }));
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    await userEvent.click(screen.getByRole("radio", { name: "System" }));
    expect(localStorage.getItem("moc-theme")).toBe("system");
  });
  it("defaults to dark when nothing is stored", () => {
    localStorage.clear();
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });
  it("hook reads stored value", () => {
    localStorage.setItem("moc-theme", "light");
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe("light");
    act(() => result.current.setTheme("dark"));
    expect(result.current.theme).toBe("dark");
  });
});

describe("presentational", () => {
  it("render content", () => {
    render(<><Badge tone="ok">ok</Badge><Kpi label="Value" value="€1" hint="h" /><EmptyState title="Nothing">sub</EmptyState></>);
    for (const t of ["ok", "Value", "€1", "h", "Nothing", "sub"]) expect(screen.getByText(t)).toBeInTheDocument();
  });
});
