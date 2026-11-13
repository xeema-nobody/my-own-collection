/* Content script on vinted.nl: works the app's publish queue one item at a time in the user's own tab.
 * Start: the app opens https://www.vinted.nl/items/new#moc-publish. Dry-run (default, popup) fills + reads back,
 * never clicks Upload and releases the item. Run state lives in the service worker, so it survives page loads. */
(function () {
  const R = globalThis.MocRecipe;
  const bg = (msg) => chrome.runtime.sendMessage(msg);
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const rand = (a, b) => a + Math.random() * (b - a);
  const path = () => location.pathname;
  const env = {
    doc: document, path,
    pause: (s) => sleep((s != null ? s : rand(0.6, 1.8)) * 1000),
    tick: () => sleep(rand(8, 25)),
    async loadPhotos(d) {
      const out = [];
      for (const [i, u] of d.photo_urls.entries()) {
        const r = await bg({ t: "photo", path: u });
        if (r.status !== 200) throw new R.Guard(`photo ${i + 1} not available (${r.status})`);
        out.push({ name: `${String(i + 1).padStart(2, "0")}.jpg`, type: "image/jpeg", bytes: Uint8Array.from(atob(r.b64), (c) => c.charCodeAt(0)) });
      }
      return out;
    },
  };

  function banner(text, kind, onStop) {
    let b = document.getElementById("moc-banner");
    if (!b) {
      b = document.createElement("div");
      b.id = "moc-banner";
      b.style.cssText = "position:fixed;top:0;left:0;right:0;z-index:2147483647;padding:8px 12px;font:13px system-ui;display:flex;gap:12px;align-items:center";
      document.documentElement.appendChild(b);
    }
    b.style.background = kind === "error" ? "#b3261e" : kind === "done" ? "#1b6e3c" : "#1d3557";
    b.style.color = "#fff";
    b.textContent = "my-own-collection: " + text;
    if (onStop) {
      const x = document.createElement("button");
      x.textContent = "Stop";
      x.onclick = onStop;
      b.appendChild(x);
    }
  }

  async function finish(text, kind) {
    await bg({ t: "stop" });
    banner(text, kind || "done");
    if (kind === "error") await bg({ t: "badge", text: "!" });
  }

  async function release(run) {
    if (run.item) await bg({ t: "api", method: "POST", path: `/api/publish/queue/${run.item.id}/release` });
  }

  async function stopByUser() {
    const run = await bg({ t: "state" });
    if (run) await release(run);
    await finish("stopped by you, item released", "error");
  }

  async function step(run) {
    banner(`${run.dry ? "DRY RUN" : "publishing"}: ${run.step}${run.item ? " - " + run.item.payload.title : ""}`, "info", stopByUser);
    await bg({ t: "badge", text: run.dry ? "dry" : "on" });
    env.allowDialog = run.step === "uploading" ? ["item listed"] : null;   // Vinted's success dialog after Upload
    R.checkPage(env);

    if (run.step === "claim") {
      if (run.resumeAt && Date.now() < run.resumeAt) { await sleep(run.resumeAt - Date.now()); }
      const s = await bg({ t: "settings" });
      if (!run.dry && s.day.n >= s.maxPerDay) return finish(`daily cap ${s.maxPerDay} reached`, "done");
      const r = await bg({ t: "api", method: "POST", path: "/api/publish/queue/next" });
      if (r.status === 409) throw new R.Guard("queue already has an item publishing: release it in Settings > Data");
      if (r.status !== 200) throw new R.Guard(`app answered ${r.status} on claim (is it running on :8100?)`);
      if (!r.body) return finish(`queue empty, ${run.published} published`, "done");
      const item = r.body;
      await bg({ t: "save", patch: { item, step: "fill" } });
      const target = new URL(item.open_url);
      if (target.pathname !== location.pathname) { location.href = item.open_url; return; }
      return step({ ...run, item, step: "fill" });
    }

    if (run.step === "fill") {
      try {
        for (let w = 0; !document.querySelector(`[data-testid='${R.TID.title}']`); w++) {   // SPA renders after load
          R.checkPage(env);
          if (w >= 15) throw new R.Guard("form did not appear (wrong page?)");
          await sleep(1000);
        }
        await R.fillForm(env, run.item);
      } catch (e) { e.item = run.item; throw e; }
      if (run.dry) {
        await release(run);
        return finish(`DRY RUN OK: "${run.item.payload.title}" filled and read back, nothing uploaded, item released`, "done");
      }
      await bg({ t: "save", patch: { step: "uploading" } });
      env.doc.querySelector(`[data-testid='${R.TID.save}']`).click();
      return step({ ...run, step: "uploading" });
    }

    if (run.step === "uploading") {                       // Upload was clicked: from here an error marks the item failed
      for (let waited = 0; !path().includes("/member/"); waited++) {
        R.checkPage(env);
        if (waited >= 30) throw new R.Guard("no redirect after Upload: " + document.body.innerText.slice(0, 200));
        await sleep(1000);
      }
      await env.pause(2.0);
      R.checkPage(env);
      if (run.item.mode === "update") return report(run, run.item.url);
      const href = R.findItemLink(document, run.item.payload.title);
      if (!href) throw new R.Guard("uploaded item not found on the profile page");
      await bg({ t: "save", patch: { step: "readurl" } });
      location.href = href;
      return;
    }

    if (run.step === "readurl") {
      if (!location.pathname.includes("/items/")) throw new R.Guard("uploaded item not found on the profile page");
      return report(run, location.href.split("?")[0].split("#")[0]);
    }
  }

  async function report(run, url) {
    const r = await bg({ t: "api", method: "POST", path: `/api/publish/queue/${run.item.id}/result`, json: { state: "published", url } });
    if (r.status !== 200) throw new R.Guard(`app refused the result (${r.status}); check Vinted for ${url}`);
    await bg({ t: "bump" });
    const published = run.published + 1;
    const gap = (90 + rand(0, 45)) * 1000;
    await bg({ t: "save", patch: { item: null, step: "claim", published, resumeAt: Date.now() + gap } });
    banner(`published ${published}: ${url}. Next item in ${Math.round(gap / 1000)} s`, "info", stopByUser);
    await sleep(gap);
    const next = await bg({ t: "state" });
    if (next) return step(next);
  }

  async function guardStop(run, e) {
    const uploadClicked = ["uploading", "readurl"].includes(run.step);
    if (run.item) {
      if (uploadClicked) await bg({ t: "api", method: "POST", path: `/api/publish/queue/${run.item.id}/result`, json: { state: "failed", error: String(e.message).slice(0, 500) } });
      else await release(run);
    }
    await finish(`${e.message}${uploadClicked ? " (marked failed: check Vinted)" : run.item ? " (item released)" : ""}`, "error");
  }

  async function main() {
    let run = await bg({ t: "state" });
    if (!run && location.hash === "#moc-publish") {
      const s = await bg({ t: "settings" });
      history.replaceState(null, "", location.pathname + location.search);
      run = { active: true, dry: s.dry, step: "claim", published: 0, item: null };
      await bg({ t: "start", run });
      run = await bg({ t: "state" });
    }
    if (!run) return;
    try { await step(run); }
    catch (e) {
      if (e instanceof R.Guard || e.name === "Guard") return guardStop((await bg({ t: "state" })) || run, e);
      return guardStop((await bg({ t: "state" })) || run, new Error("unexpected error: " + e.message));
    }
  }

  main();
})();
