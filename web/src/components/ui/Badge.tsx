import type { ReactNode } from "react";
import { cx } from "./cx";

const tones = {
  neutral: "bg-surface-2 text-muted",
  accent: "bg-accent/15 text-accent",
  ok: "bg-ok/15 text-ok",
  warn: "bg-warn/15 text-warn",
  danger: "bg-danger/15 text-danger",
};

export function Badge({ tone = "neutral", className, title, children }: { tone?: keyof typeof tones; className?: string; title?: string; children: ReactNode }) {
  return <span title={title} className={cx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium", tones[tone], className)}>{children}</span>;
}
