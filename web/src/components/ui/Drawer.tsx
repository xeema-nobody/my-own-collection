import * as RD from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ReactNode } from "react";

/** Right-side panel for row details (Radix Dialog: focus trap, Esc to close). */
export function Drawer({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode }) {
  return (
    <RD.Root open={open} onOpenChange={(o) => !o && onClose()}>
      <RD.Portal>
        <RD.Overlay className="fixed inset-0 z-40 bg-black/50" />
        <RD.Content aria-describedby={undefined} className="fixed inset-y-0 right-0 z-50 w-full max-w-2xl overflow-y-auto bg-bg p-5 shadow-lg">
          <div className="mb-4 flex items-start justify-between gap-3">
            <RD.Title className="text-lg font-semibold">{title}</RD.Title>
            <RD.Close aria-label="Close" className="rounded p-1 text-muted hover:bg-surface-2 hover:text-fg"><X size={18} /></RD.Close>
          </div>
          {children}
        </RD.Content>
      </RD.Portal>
    </RD.Root>);
}
