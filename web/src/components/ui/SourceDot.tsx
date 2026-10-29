import { SOURCE_COLOR, sourceLabel } from "../../lib/colors";

/** Coloured dot + source name. */
export function SourceDot({ source, label = true }: { source: string; label?: boolean }) {
  return <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 shrink-0 rounded-full" style={{ background: SOURCE_COLOR[source] ?? "rgb(var(--muted))" }} aria-hidden />{label && sourceLabel(source)}</span>;
}
