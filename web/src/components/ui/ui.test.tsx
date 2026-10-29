import { describe, expect, it, vi } from "vitest";
import { render, renderHook, act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Combobox, Section, SegmentedControl, Badge, Kpi, EmptyState, Pagination, SortTh, Drawer } from "./index";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
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

describe("Pagination", () => {
  it("shows the range and disables prev on page 1", async () => {
    const on = vi.fn();
    render(<Pagination page={1} pageSize={50} total={120} onPage={on} onPageSize={() => {}} />);
    expect(screen.getByText("1-50 of 120")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous page" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(on).toHaveBeenCalledWith(2);
  });
  it("last page disables next; empty total reads 0-0", () => {
    const { rerender } = render(<Pagination page={3} pageSize={50} total={120} onPage={() => {}} onPageSize={() => {}} />);
    expect(screen.getByText("101-120 of 120")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();
    rerender(<Pagination page={1} pageSize={50} total={0} onPage={() => {}} onPageSize={() => {}} />);
    expect(screen.getByText("0-0 of 0")).toBeInTheDocument();
  });
});

describe("SortTh", () => {
  it("exposes sort direction and fires onSort", async () => {
    const on = vi.fn();
    render(<table><thead><tr><SortTh label="Value" active dir="asc" onSort={on} /><SortTh label="Cost" active={false} dir="desc" onSort={() => {}} /></tr></thead></table>);
    expect(screen.getByRole("columnheader", { name: "Value" })).toHaveAttribute("aria-sort", "ascending");
    expect(screen.getByRole("columnheader", { name: "Cost" })).toHaveAttribute("aria-sort", "none");
    await userEvent.click(screen.getByRole("button", { name: "Value" }));
    expect(on).toHaveBeenCalled();
  });
});

describe("Drawer", () => {
  it("renders content when open and closes on the close button", async () => {
    const on = vi.fn();
    render(<Drawer open onClose={on} title="Details"><p>body</p></Drawer>);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(on).toHaveBeenCalled();
  });
  it("renders nothing when closed", () => {
    render(<Drawer open={false} onClose={() => {}} title="Details"><p>body</p></Drawer>);
    expect(screen.queryByText("body")).not.toBeInTheDocument();
  });
});

describe("Combobox", () => {
  const wrap = (ui: React.ReactElement) => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>);
  it("searches, pages and selects", async () => {
    const fetchPage = vi.fn(async (q: string, page: number) => ({
      options: q === "zzz" ? [] : [{ value: `a${page}`, label: `Alpha ${page}` }], more: page < 2 && q !== "zzz" }));
    wrap(<Combobox aria-label="Card" cacheKey="t" value="" onChange={vi.fn()} fetchPage={fetchPage} />);
    await userEvent.click(screen.getByRole("button", { name: "Card" }));
    expect(await screen.findByText("Alpha 1")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Show more" }));
    expect(await screen.findByText("Alpha 2")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Show more" })).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Search"), "zzz");
    expect(await screen.findByText("No matches")).toBeInTheDocument();
    expect(fetchPage).toHaveBeenCalledWith("zzz", 1);
  });
  it("reports the clicked option", async () => {
    const on = vi.fn();
    wrap(<Combobox aria-label="Card" cacheKey="t2" value="" onChange={on} fetchPage={async () => ({ options: [{ value: "x", label: "Xatu" }], more: false })} />);
    await userEvent.click(screen.getByRole("button", { name: "Card" }));
    await userEvent.click(await screen.findByRole("button", { name: "Xatu" }));
    expect(on).toHaveBeenCalledWith("x", "Xatu");
  });
});
