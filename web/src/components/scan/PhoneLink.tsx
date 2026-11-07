import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import QRCode from "qrcode";
import { Copy } from "lucide-react";
import { api } from "../../lib/api";
import { QueryError } from "../QueryState";
import { Button, Skeleton } from "../ui";

/** Laptop side of "Add by scanning": the phone's address as a QR code, or what to do when it is not set up. */
export default function PhoneLink() {
  const st = useQuery({ queryKey: ["scan", "status"], queryFn: api.scanStatus, staleTime: 60_000 });
  const [qr, setQr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const url = st.data?.enabled ? st.data.url : null;
  useEffect(() => {
    if (!url) { setQr(null); return; }
    QRCode.toDataURL(url, { margin: 1, width: 240, color: { dark: "#000000", light: "#ffffff" } }).then(setQr).catch(() => setQr(null));
  }, [url]);
  if (st.isLoading) return <Skeleton className="h-60 w-60" />;
  if (st.isError) return <QueryError q={st} label="Phone link" />;
  if (!url) return (
    <div className="space-y-3 text-sm">
      <p>The phone link is not set up yet. One time only:</p>
      <ol className="list-decimal space-y-1 pl-5 text-muted">
        <li>Install Tailscale on this computer and on your phone, and sign in to the same account on both.</li>
        <li>In the Tailscale admin page turn on <b>MagicDNS</b> and <b>HTTPS certificates</b>.</li>
        <li>Run <code className="rounded bg-surface-2 px-1">scripts/lan.sh setup &lt;computer-name&gt;.&lt;tailnet&gt;.ts.net &lt;your-tailscale-login&gt;</code></li>
        <li>Run <code className="rounded bg-surface-2 px-1">docker compose up -d app</code>, then <code className="rounded bg-surface-2 px-1">scripts/lan.sh up</code> and the <code className="rounded bg-surface-2 px-1">tailscale serve</code> line it prints.</li>
      </ol>
      <p className="text-muted">Details: docs/README.md, "Scan cards with your phone".</p>
    </div>);
  return (
    <div className="space-y-3 text-sm">
      {qr ? <img src={qr} alt={`QR code for ${url}`} width={240} height={240} className="rounded bg-white p-1" /> : <Skeleton className="h-60 w-60" />}
      <p>Point the phone camera at the code (phone with Tailscale on). It opens the scan page{st.data?.login ? <> for <b>{st.data.login}</b></> : null}.</p>
      <div className="flex items-center gap-2">
        <code className="min-w-0 flex-1 truncate rounded bg-surface-2 px-2 py-1">{url}</code>
        <Button variant="secondary" size="sm" onClick={() => navigator.clipboard?.writeText(url).then(() => setCopied(true))}><Copy size={12} />{copied ? "Copied" : "Copy"}</Button>
      </div>
      <p className="text-muted">On the phone you can add the page to the home screen. Cards you add show up here at once.</p>
    </div>);
}
