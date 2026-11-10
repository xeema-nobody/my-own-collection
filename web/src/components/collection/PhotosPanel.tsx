import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Star, Trash2, Upload } from "lucide-react";
import { api, photoUrl, type PhotoKind } from "../../lib/api";
import { Button, Select } from "../ui";

const KINDS: { value: PhotoKind; label: string }[] = [
  { value: "front", label: "Front" }, { value: "back", label: "Back" }, { value: "corner", label: "Corner" }, { value: "surface", label: "Surface" },
  { value: "slab_front", label: "Slab front" }, { value: "slab_back", label: "Slab back" }, { value: "other", label: "Other" }];
const kindLabel = (k: PhotoKind) => KINDS.find((x) => x.value === k)?.label ?? k;

/** Photos of one stack (kept compressed in the database, used for listings). Cover = first shown. */
export default function PhotosPanel({ id, graded }: { id: string; graded?: boolean }) {
  const qc = useQueryClient();
  const file = useRef<HTMLInputElement>(null);
  const [kind, setKind] = useState<PhotoKind>(graded ? "slab_front" : "front");
  const list = useQuery({ queryKey: ["photos", id], queryFn: () => api.photos(id) });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["photos", id] }); qc.invalidateQueries({ queryKey: ["collection"] }); qc.invalidateQueries({ queryKey: ["photos", "stats"] }); };
  const upload = useMutation({
    mutationFn: async (files: File[]) => { for (const f of files) await api.uploadPhoto(id, f, kind); },
    onSettled: refresh,
  });
  const patch = useMutation({ mutationFn: ({ pid, b }: { pid: string; b: Parameters<typeof api.patchPhoto>[1] }) => api.patchPhoto(pid, b), onSettled: refresh });
  const del = useMutation({ mutationFn: (pid: string) => api.deletePhoto(pid), onSettled: refresh });
  const photos = Array.isArray(list.data) ? list.data : [];
  const err = (upload.error ?? patch.error ?? del.error) as Error | null;
  return (
    <section className="space-y-2 border-t border-line pt-3" aria-label="Photos">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">Photos{photos.length ? ` (${photos.length})` : ""}</h3>
        <div className="flex items-center gap-2">
          <div className="w-32"><Select aria-label="Photo kind" value={kind} onChange={(v) => setKind(v as PhotoKind)} options={KINDS} /></div>
          <Button variant="secondary" size="sm" disabled={upload.isPending} onClick={() => file.current?.click()}><Upload size={12} />{upload.isPending ? "Uploading…" : "Add photos"}</Button>
          <input ref={file} type="file" accept="image/jpeg,image/png,image/webp" multiple className="hidden" aria-label="Choose photos"
            onChange={(e) => { const fs = Array.from(e.target.files ?? []); e.target.value = ""; if (fs.length) upload.mutate(fs); }} />
        </div>
      </div>
      {err && <p role="alert" className="text-sm text-danger">{err.message}</p>}
      {photos.length === 0
        ? <p className="text-sm text-muted">No photos yet. Scanning from the phone saves one; you can also add them here.</p>
        : <ul className="grid grid-cols-3 gap-2 sm:grid-cols-4">
          {photos.map((p, i) => (
            <li key={p.id} className="space-y-1">
              <a href={photoUrl(p.id)} target="_blank" rel="noreferrer" className="relative block overflow-hidden rounded border border-line">
                <img src={photoUrl(p.id, "thumb")} alt={`${kindLabel(p.kind)} photo`} className="aspect-[63/88] w-full object-cover" loading="lazy" />
                {p.cover && <span className="absolute left-1 top-1 rounded bg-accent px-1.5 text-[10px] font-medium text-accent-fg">Cover</span>}
              </a>
              <div className="flex items-center justify-between text-xs text-muted">
                <span>{kindLabel(p.kind)}</span>
                <span className="flex gap-0.5">
                  <button type="button" aria-label="Move earlier" disabled={i === 0} className="p-1 disabled:opacity-30" onClick={() => patch.mutate({ pid: p.id, b: { position: i - 1 } })}><ArrowLeft size={12} /></button>
                  <button type="button" aria-label="Move later" disabled={i === photos.length - 1} className="p-1 disabled:opacity-30" onClick={() => patch.mutate({ pid: p.id, b: { position: i + 1 } })}><ArrowRight size={12} /></button>
                  <button type="button" aria-label="Make cover" disabled={p.cover} className="p-1 disabled:opacity-30" onClick={() => patch.mutate({ pid: p.id, b: { cover: true } })}><Star size={12} /></button>
                  <button type="button" aria-label="Delete photo" className="p-1 text-danger" onClick={() => del.mutate(p.id)}><Trash2 size={12} /></button>
                </span>
              </div>
            </li>))}
        </ul>}
    </section>);
}
