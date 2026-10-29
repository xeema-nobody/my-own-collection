import { useState } from "react";
import type { UseQueryResult } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { ago } from "../../lib/api";
import { durationSec, fmtDuration, jobLabel, jobSummary, jobTone } from "../../lib/jobs";
import { Badge, Chip, EmptyState, Table, THead, Td, Th, Tr } from "../../components/ui";

const LIMIT = 20;

export default function JobsTab({ jobs }: { jobs: UseQueryResult<any[]> }) {
  const [type, setType] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const all = jobs.data ?? [];
  const types = [...new Set(all.map((j) => j.type as string))];
  const rows = all.filter((j) => !type || j.type === type).slice(0, LIMIT);
  if (!all.length && !jobs.isLoading) return <EmptyState title="No jobs yet">Imports, refreshes and fetches show up here.</EmptyState>;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Job type">
        <Chip active={type === ""} onClick={() => setType("")}>All</Chip>
        {types.map((t) => <Chip key={t} active={type === t} onClick={() => setType(t)}>{jobLabel(t)}</Chip>)}
        <span className="ml-auto text-xs text-muted">last {LIMIT}</span>
      </div>
      <Table>
        <THead><Th className="w-6" /><Th>Job</Th><Th>Status</Th><Th>Trigger</Th><Th>Started</Th><Th num>Duration</Th><Th>Summary</Th></THead>
        <tbody>
          {rows.map((j) => {
            const id = String(j.id), isOpen = open === id;
            return [
              <Tr key={id}>
                <Td><button type="button" aria-label={`${isOpen ? "Hide" : "Show"} details for ${jobLabel(j.type)}`} aria-expanded={isOpen} onClick={() => setOpen(isOpen ? null : id)}>
                  <ChevronRight size={14} className={isOpen ? "rotate-90 transition" : "transition"} aria-hidden /></button></Td>
                <Td className="whitespace-nowrap font-medium">{jobLabel(j.type)}</Td>
                <Td><Badge tone={jobTone(j.status)}>{j.status}</Badge></Td>
                <Td className="text-muted">{j.trigger ?? "manual"}</Td>
                <Td className="whitespace-nowrap text-muted" title={j.started_at}>{ago(j.started_at)}</Td>
                <Td num className="whitespace-nowrap">{fmtDuration(durationSec(j.started_at, j.finished_at))}</Td>
                <Td className={j.error ? "text-danger" : "text-muted"} title={j.error ?? ""}>{jobSummary(j)}</Td>
              </Tr>,
              isOpen && <Tr key={id + "d"}><Td colSpan={7}><pre className="max-h-64 overflow-auto rounded bg-surface-2 p-3 text-xs">{JSON.stringify({ started_at: j.started_at, finished_at: j.finished_at, error: j.error, stats: j.stats }, null, 2)}</pre></Td></Tr>,
            ];
          })}
        </tbody>
      </Table>
    </div>);
}
