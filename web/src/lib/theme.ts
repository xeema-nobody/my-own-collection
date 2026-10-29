import { useEffect, useState } from "react";

export type Theme = "light" | "dark" | "system";
const KEY = "moc-theme";

function stored(): Theme {
  try { const v = localStorage.getItem(KEY); if (v === "light" || v === "dark") return v; } catch { /* storage blocked */ }
  return "system";
}

/** Toggle the `dark` class on <html>; "system" follows the OS. */
export function applyTheme(t: Theme) {
  const dark = t === "dark" || (t === "system" && matchMedia?.("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(stored);
  const setTheme = (t: Theme) => {
    try { t === "system" ? localStorage.removeItem(KEY) : localStorage.setItem(KEY, t); } catch { /* storage blocked */ }
    setThemeState(t);
  };
  useEffect(() => {
    applyTheme(theme);
    if (theme !== "system" || !matchMedia) return;
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const on = () => applyTheme("system");
    mq.addEventListener?.("change", on);
    return () => mq.removeEventListener?.("change", on);
  }, [theme]);
  return { theme, setTheme };
}
