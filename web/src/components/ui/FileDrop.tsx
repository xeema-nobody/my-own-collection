import { useRef, useState } from "react";
import { Upload } from "lucide-react";
import { cx } from "./cx";

/** Click or drop a single file. The hidden input keeps keyboard and test access. */
export function FileDrop({ file, onFile, accept, hint }: { file: File | null; onFile: (f: File | null) => void; accept: string; hint: string }) {
  const ref = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  return (
    <div role="button" tabIndex={0} onClick={() => ref.current?.click()}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), ref.current?.click())}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); onFile(e.dataTransfer.files?.[0] ?? null); }}
      className={cx("flex cursor-pointer flex-col items-center gap-1 rounded-lg border-2 border-dashed px-4 py-6 text-center text-sm transition",
        over ? "border-accent bg-accent/10" : "border-line hover:border-muted")}>
      <Upload size={20} className="text-muted" aria-hidden />
      <span className={file ? "font-medium" : "text-muted"}>{file ? file.name : hint}</span>
      <input ref={ref} type="file" accept={accept} className="sr-only" tabIndex={-1} onClick={(e) => e.stopPropagation()}
        onChange={(e) => onFile(e.target.files?.[0] ?? null)} />
    </div>);
}
