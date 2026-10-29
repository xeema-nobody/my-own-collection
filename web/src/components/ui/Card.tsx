import { useState, type ReactNode } from "react";
import * as Collapsible from "@radix-ui/react-collapsible";
import { ChevronDown } from "lucide-react";
import { cx } from "./cx";

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cx("rounded-lg bg-surface p-4 shadow-card", className)}>{children}</div>;
}

function usePersisted(key: string | undefined, initial: boolean) {
  const [open, set] = useState(() => {
    try { const v = key ? localStorage.getItem(`moc-open:${key}`) : null; return v == null ? initial : v === "1"; } catch { return initial; }
  });
  const setOpen = (v: boolean) => { set(v); try { key && localStorage.setItem(`moc-open:${key}`, v ? "1" : "0"); } catch { /* storage blocked */ } };
  return [open, setOpen] as const;
}

/** Titled card. With `collapsible`, the open state is remembered under `id`. */
export function Section({ title, actions, collapsible, id, defaultOpen = true, className, children }: {
  title: ReactNode; actions?: ReactNode; collapsible?: boolean; id?: string; defaultOpen?: boolean; className?: string; children: ReactNode;
}) {
  const [open, setOpen] = usePersisted(collapsible ? id : undefined, defaultOpen);
  const head = <h2 className="text-sm font-semibold tracking-wide text-muted uppercase">{title}</h2>;
  if (!collapsible) return (
    <Card className={className}>
      <div className="mb-3 flex items-center justify-between gap-2">{head}{actions}</div>{children}
    </Card>);
  return (
    <Card className={className}>
      <Collapsible.Root open={open} onOpenChange={setOpen}>
        <div className="flex items-center justify-between gap-2">
          <Collapsible.Trigger className="flex items-center gap-1.5 rounded" aria-label={`Toggle ${typeof title === "string" ? title : "section"}`}>
            <ChevronDown size={16} className={cx("text-muted transition", !open && "-rotate-90")} />{head}
          </Collapsible.Trigger>{actions}
        </div>
        <Collapsible.Content className="mt-3">{children}</Collapsible.Content>
      </Collapsible.Root>
    </Card>);
}
