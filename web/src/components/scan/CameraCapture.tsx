import { useEffect, useRef, useState } from "react";
import { Camera, Image as ImageIcon } from "lucide-react";
import { Button } from "../ui";
import { CARD_RATIO, cropToJpeg, guideRect, resizePhoto } from "../../lib/scan";

const canStream = () => typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia && (typeof window === "undefined" || window.isSecureContext !== false);

/** Live rear camera with a card-shaped guide and tap to capture. Without a camera (or on a page that is not
 *  https) the native camera app is used through a file input; both paths hand one JPEG to `onPhoto`. */
export default function CameraCapture({ onPhoto, busy }: { onPhoto: (photo: Blob) => void; busy?: boolean }) {
  const video = useRef<HTMLVideoElement>(null);
  const file = useRef<HTMLInputElement>(null);
  const [live, setLive] = useState(false);
  const [note, setNote] = useState<string | null>(canStream() ? null : "Live camera needs the secure (https) link, so the phone's own camera is used instead.");

  useEffect(() => {
    if (!canStream()) return;
    let stream: MediaStream | undefined, gone = false;
    navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 } }, audio: false })
      .then((s) => {
        if (gone) { s.getTracks().forEach((t) => t.stop()); return; }
        stream = s;
        if (video.current) { video.current.srcObject = s; video.current.play().catch(() => undefined); }
        setLive(true);
      })
      .catch((e: Error) => setNote(e.name === "NotAllowedError"
        ? "Camera is blocked for this page. Allow it in the browser's site settings, or use the phone's own camera below."
        : "No usable camera found. Use the phone's own camera below."));
    return () => { gone = true; stream?.getTracks().forEach((t) => t.stop()); };
  }, []);

  const snap = async () => {
    const v = video.current;
    if (!v || !v.videoWidth) return;
    onPhoto(await cropToJpeg(v, guideRect(v.videoWidth, v.videoHeight)));
  };
  const picked = async (f?: File) => { if (f) onPhoto(await resizePhoto(f)); };

  return (
    <div className="space-y-3">
      <div className="relative mx-auto aspect-[3/4] w-full max-w-sm overflow-hidden rounded-lg bg-surface-2">
        <video ref={video} playsInline muted aria-label="Camera view" className="h-full w-full object-cover" />
        {live && <div aria-hidden className="pointer-events-none absolute left-1/2 top-1/2 w-[70%] -translate-x-1/2 -translate-y-1/2 rounded-xl border-2 border-accent/90 shadow-[0_0_0_999px_rgba(0,0,0,0.45)]" style={{ aspectRatio: String(CARD_RATIO) }} />}
        {!live && <p className="absolute inset-0 grid place-items-center p-6 text-center text-sm text-muted">{note ?? "Starting camera…"}</p>}
      </div>
      {live && <p className="text-center text-xs text-muted">Fit the card in the frame, name at the top. Less glare reads better.</p>}
      <div className="mx-auto flex max-w-sm gap-2">
        {live && <Button className="flex-1 py-3 text-base" disabled={busy} onClick={snap}><Camera size={18} />Scan</Button>}
        <Button variant="secondary" className={live ? "py-3" : "flex-1 py-3 text-base"} disabled={busy} onClick={() => file.current?.click()}>
          <ImageIcon size={18} />{live ? "Photo" : "Take a photo"}</Button>
        <input ref={file} type="file" accept="image/*" capture="environment" className="hidden" aria-label="Take a photo of the card"
          onChange={(e) => { picked(e.target.files?.[0]); e.target.value = ""; }} />
      </div>
    </div>);
}
