import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

// jsdom lacks ResizeObserver (recharts' ResponsiveContainer needs it).
globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} };

// jsdom lacks matchMedia (theme hook).
globalThis.matchMedia ??= ((q: string) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {} })) as unknown as typeof matchMedia;

// jsdom lacks pointer capture / scrollIntoView (Radix Select opens via pointer events).
Element.prototype.hasPointerCapture ??= () => false;
Element.prototype.setPointerCapture ??= () => {};
Element.prototype.releasePointerCapture ??= () => {};
Element.prototype.scrollIntoView ??= () => {};
