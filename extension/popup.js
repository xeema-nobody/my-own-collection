const $ = (id) => document.getElementById(id);
async function refresh() {
  const s = await chrome.runtime.sendMessage({ t: "settings" });
  const run = await chrome.runtime.sendMessage({ t: "state", any: true });
  $("dry").checked = s.dry;
  $("info").textContent = `Today: ${s.day.n}/${s.maxPerDay} uploaded. ` + (run ? `Run active (${run.dry ? "dry" : "real"}, ${run.step}).` : "No run active.");
}
$("dry").onchange = async () => { await chrome.runtime.sendMessage({ t: "setDry", dry: $("dry").checked }); refresh(); };
$("stop").onclick = async () => {
  const run = await chrome.runtime.sendMessage({ t: "state", any: true });
  if (run && run.item) await chrome.runtime.sendMessage({ t: "api", method: "POST", path: `/api/publish/queue/${run.item.id}/release` });
  await chrome.runtime.sendMessage({ t: "stop" });
  refresh();
};
refresh();
