import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { presetActive, useUrlState } from "./urlState";

const D = { q: "", sort: "added", page: "1" };
const wrap = (route: string) => ({ children }: { children: ReactNode }) => <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>;
const both = () => ({ s: useUrlState(D), loc: useLocation() });

describe("useUrlState", () => {
  it("reads params over defaults and ignores unknown ones", () => {
    const { result } = renderHook(both, { wrapper: wrap("/?q=char&junk=1&page=3") });
    expect(result.current.s[0]).toEqual({ q: "char", sort: "added", page: "3" });
  });
  it("leaves defaults out of the URL and resets the page on a filter change", () => {
    const { result } = renderHook(both, { wrapper: wrap("/?page=3&sort=value") });
    act(() => result.current.s[1]({ q: "pika" }));
    expect(result.current.loc.search).toBe("?q=pika&sort=value");   // page back to 1 = default = omitted
    act(() => result.current.s[1]({ sort: "added" }));
    expect(result.current.loc.search).toBe("?q=pika");
  });
  it("keepPage keeps the page (paging itself)", () => {
    const { result } = renderHook(both, { wrapper: wrap("/") });
    act(() => result.current.s[1]({ page: "2" }, true));
    expect(result.current.loc.search).toBe("?page=2");
  });
});

describe("presetActive", () => {
  const keys = ["q", "sort"];
  it("is active when the preset's keys match and missing keys mean default", () => {
    expect(presetActive({ q: "", sort: "added" }, D, {}, keys)).toBe(true);
    expect(presetActive({ q: "x", sort: "added" }, D, { q: "x" }, keys)).toBe(true);
    expect(presetActive({ q: "x", sort: "value" }, D, { q: "x" }, keys)).toBe(false);
  });
});
