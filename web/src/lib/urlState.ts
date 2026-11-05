import { useSearchParams } from "react-router-dom";

/**
 * Page state kept in the address bar (back button, bookmarks). Values are strings; a value equal to
 * its default is left out of the URL. `page` (when present in `defaults`) goes back to 1 on any
 * change unless `keepPage`. Unknown params are ignored.
 */
export function useUrlState<T extends Record<string, string>>(defaults: T) {
  const [sp, setSp] = useSearchParams();
  const state = { ...defaults } as T;
  for (const k of Object.keys(defaults)) { const v = sp.get(k); if (v !== null) (state as Record<string, string>)[k] = v; }
  const set = (patch: Partial<T>, keepPage = false) => {
    const next: Record<string, string> = { ...state, ...(keepPage || !("page" in defaults) ? {} : { page: "1" }), ...patch } as Record<string, string>;
    setSp(Object.fromEntries(Object.entries(next).filter(([k, v]) => v !== defaults[k])), { replace: true });
  };
  return [state, set] as const;
}

/** True when every key in `query` equals the state's value (missing keys = the default), so a preset shows as active. */
export function presetActive(state: Record<string, string>, defaults: Record<string, string>, query: Record<string, string>, keys: readonly string[]) {
  return keys.every((k) => (state[k] ?? defaults[k] ?? "") === (query[k] ?? defaults[k] ?? ""));
}
