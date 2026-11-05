import { useState } from "react";

/** useState remembered in localStorage (per-device UI preference). Falls back silently if storage is unavailable. */
export function useStoredState<T extends string>(key: string, initial: T, allowed?: readonly T[]) {
  const [v, setV] = useState<T>(() => {
    try { const s = localStorage.getItem(key) as T | null; if (s && (!allowed || allowed.includes(s))) return s; } catch { /* private mode */ }
    return initial;
  });
  const set = (n: T) => { setV(n); try { localStorage.setItem(key, n); } catch { /* ignore */ } };
  return [v, set] as const;
}
