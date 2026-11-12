/* Service worker: the only place that talks to the app (http://localhost:8100) and holds run state. */
const API = "http://localhost:8100";
const DEFAULTS = { dry: true, maxPerDay: 10, minGapS: 90 };

const today = () => new Date().toISOString().slice(0, 10);

async function settings() {
  const s = await chrome.storage.local.get(["dry", "day"]);
  return { ...DEFAULTS, dry: s.dry !== false, day: s.day && s.day.day === today() ? s.day : { day: today(), n: 0 } };
}

async function api(method, path, json) {
  const r = await fetch(API + path, { method, headers: json ? { "content-type": "application/json" } : {}, body: json ? JSON.stringify(json) : undefined });
  let body = null;
  try { body = await r.json(); } catch { /* empty */ }
  return { status: r.status, body };
}

async function photo(path) {
  const r = await fetch(API + path);
  if (!r.ok) return { status: r.status };
  const bytes = new Uint8Array(await r.arrayBuffer());
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return { status: 200, b64: btoa(bin) };
}

async function handle(msg, sender) {
  const tab = sender.tab && sender.tab.id;
  switch (msg.t) {
    case "settings": return settings();
    case "setDry": await chrome.storage.local.set({ dry: !!msg.dry }); return true;
    case "bump": { const s = await settings(); await chrome.storage.local.set({ day: { day: today(), n: s.day.n + 1 } }); return true; }
    case "api": return api(msg.method, msg.path, msg.json);
    case "photo": return photo(msg.path);
    case "state": {
      const { run } = await chrome.storage.session.get("run");
      return run && (run.tab === tab || msg.any) ? run : null;       // only the tab that started the run works it
    }
    case "start": await chrome.storage.session.set({ run: { ...msg.run, tab } }); return true;
    case "save": {
      const { run } = await chrome.storage.session.get("run");
      if (!run || run.tab !== tab) return false;
      await chrome.storage.session.set({ run: { ...run, ...msg.patch } });
      return true;
    }
    case "stop": await chrome.storage.session.remove("run"); await chrome.action.setBadgeText({ text: "" }); return true;
    case "badge": await chrome.action.setBadgeText({ text: msg.text || "" }); return true;
    default: return null;
  }
}

chrome.runtime.onMessage.addListener((msg, sender, send) => {
  handle(msg, sender).then(send, (e) => send({ error: String(e) }));
  return true;
});
