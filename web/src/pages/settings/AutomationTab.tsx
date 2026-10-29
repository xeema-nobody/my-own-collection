import type { UseQueryResult } from "@tanstack/react-query";
import { Badge, Section } from "../../components/ui";
import FetcherBadge from "../../components/FetcherBadge";

export default function AutomationTab({ status }: { status: UseQueryResult<any> }) {
  const s = status.data;
  if (!s) return null;
  return (
    <div className="space-y-4">
      <Section title="Status">
        <dl className="grid grid-cols-[10rem_1fr] gap-y-2 text-sm">
          <dt className="text-muted">Base currency</dt><dd>{s.base_currency}</dd>
          <dt className="text-muted">Scheduler</dt><dd><Badge tone={s.scheduler_enabled ? "ok" : "neutral"}>{s.scheduler_enabled ? "on" : "off (manual)"}</Badge></dd>
          <dt className="text-muted">Price fetcher</dt><dd><FetcherBadge /></dd>
        </dl>
      </Section>
      <Section title="Scheduled runs">
        {s.scheduler_enabled
          ? <ul className="space-y-1 text-sm">{s.scheduler.jobs.map((j: any) => (
              <li key={j.id} className="flex justify-between gap-4"><span>{j.id}</span><span className="num text-muted">next {j.next_run?.slice(0, 16).replace("T", " ") ?? "—"}</span></li>))}</ul>
          : <p className="text-sm text-muted">The scheduler is off. Set <code>SCHEDULER_ENABLED=true</code> and restart the app to run catalog imports, price refreshes and snapshots on a timer. Everything here still works manually.</p>}
        <p className="mt-3 text-xs text-muted">A scheduled run that cannot start (a job of that type is already running, or the fetcher is down) is logged as skipped on the Jobs tab and raises a notice in the Alerts inbox.</p>
      </Section>
    </div>);
}
