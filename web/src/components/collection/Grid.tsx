import { Link } from "react-router-dom";
import { Checkbox, cx } from "../ui";
import { money } from "../../lib/api";
import { AcqBadge } from "../AcquiredForm";
import { Value, detail } from "./parts";

/** Image-grid view of the collection page: one tile per stack; click opens the same details drawer as the table row. */
export default function Grid({ items, picked, onToggle, onOpen }: {
  items: any[]; picked: Set<string>; onToggle: (id: string) => void; onOpen: (i: any) => void;
}) {
  return (
    <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6" aria-label="Collection grid">
      {items.map((i) => (
        <li key={i.id} className={cx("group relative flex cursor-pointer flex-col gap-1.5 rounded-lg border bg-surface p-2 text-sm hover:bg-surface-2",
          picked.has(i.id) ? "border-accent" : "border-line")} onClick={() => onOpen(i)}>
          <span className="absolute left-2.5 top-2.5 z-10 rounded bg-surface/80 p-0.5" onClick={(e) => e.stopPropagation()}>
            <Checkbox aria-label={`Select ${i.card?.name} ${detail(i)}`} label="" checked={picked.has(i.id)} onChange={() => onToggle(i.id)} /></span>
          {i.quantity > 1 && <span className="absolute right-2.5 top-2.5 z-10 rounded-full bg-surface/90 px-1.5 text-xs font-semibold num">×{i.quantity}</span>}
          {i.card?.images?.small
            ? <img src={i.card.images.small} alt="" loading="lazy" className="aspect-[5/7] w-full rounded object-contain" />
            : <div className="aspect-[5/7] w-full rounded bg-surface-2" />}
          <Link to={`/cards/${encodeURIComponent(i.card_id)}`} onClick={(e) => e.stopPropagation()} className="truncate font-medium hover:underline">{i.card?.name}</Link>
          <span className="truncate text-xs text-muted">{i.card?.set?.name} #{i.card?.number} · {detail(i)}</span>
          <div className="flex flex-wrap items-center justify-between gap-1"><Value i={i} />
            <span className={cx("num text-xs", i.pl == null ? "text-muted" : i.pl >= 0 ? "text-ok" : "text-danger")} title="Profit / loss">{i.pl == null ? "" : money(i.pl)}</span></div>
          <AcqBadge type={i.acquired?.type} />
        </li>))}
    </ul>);
}
