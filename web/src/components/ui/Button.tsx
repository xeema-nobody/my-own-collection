import type { ButtonHTMLAttributes } from "react";
import { cx } from "./cx";

const variants = {
  primary: "bg-accent text-accent-fg hover:opacity-90",
  secondary: "border border-line bg-surface hover:bg-surface-2",
  ghost: "hover:bg-surface-2",
  danger: "bg-danger text-white hover:opacity-90",
};
const sizes = { sm: "px-2 py-1 text-xs", md: "px-3 py-1.5 text-sm" };

type Props = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: keyof typeof variants; size?: keyof typeof sizes };

export function Button({ variant = "primary", size = "md", className, type = "button", ...p }: Props) {
  return <button type={type} className={cx("inline-flex items-center justify-center gap-1.5 rounded font-medium transition disabled:pointer-events-none disabled:opacity-50", variants[variant], sizes[size], className)} {...p} />;
}
