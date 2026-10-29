import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme, type Theme } from "../lib/theme";
import { cx } from "./ui";

const OPTS: { value: Theme; label: string; Icon: typeof Sun }[] = [
  { value: "light", label: "Light", Icon: Sun }, { value: "system", label: "System", Icon: Monitor }, { value: "dark", label: "Dark", Icon: Moon },
];

export default function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  return (
    <div role="radiogroup" aria-label="Theme" className="inline-flex rounded bg-surface-2 p-0.5">
      {OPTS.map(({ value, label, Icon }) => (
        <button key={value} type="button" role="radio" aria-checked={theme === value} aria-label={label} title={label} onClick={() => setTheme(value)}
          className={cx("rounded p-1.5 transition", theme === value ? "bg-surface text-fg shadow-sm" : "text-muted hover:text-fg")}><Icon size={14} /></button>))}
    </div>);
}
