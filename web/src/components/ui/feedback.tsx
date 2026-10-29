import type { ReactNode } from "react";
import { cx } from "./cx";

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cx("animate-pulse rounded bg-surface-2", className)} />;
}

export function EmptyState({ title, children }: { title: ReactNode; children?: ReactNode }) {
  return <div className="rounded-lg border border-dashed border-line p-8 text-center"><p className="font-medium">{title}</p>{children && <p className="mt-1 text-sm text-muted">{children}</p>}</div>;
}
