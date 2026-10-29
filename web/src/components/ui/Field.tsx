import type { InputHTMLAttributes, ReactNode } from "react";
import { cx } from "./cx";

/** Label above a control. */
export function Field({ label, className, children }: { label: ReactNode; className?: string; children: ReactNode }) {
  return <label className={cx("block text-xs font-medium text-muted", className)}><span className="mb-1 block">{label}</span>{children}</label>;
}

export function Input({ className, ...p }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cx("w-full rounded border border-line bg-surface px-2.5 py-1.5 text-sm text-fg placeholder:text-muted", className)} {...p} />;
}

export function Checkbox({ label, className, ...p }: Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & { label: ReactNode }) {
  return <label className={cx("flex cursor-pointer items-center gap-2 text-sm", className)}><input type="checkbox" className="h-4 w-4 accent-[rgb(var(--accent))]" {...p} />{label}</label>;
}
