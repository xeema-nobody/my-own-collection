/* Vinted form recipe in the page (port of fetcher/fetcher/publisher/recipe.py; docs/vinted-sell-flow.md).
 * Steps never decide to continue past something odd: any surprise throws Guard and the run stops.
 * Nothing here solves or dismisses a CAPTCHA, login or dialog. Plain script: browser global MocRecipe or CommonJS. */
(function (root) {
  const TID = {
    photos: "add-photos-input", title: "title--input", description: "description--input",
    category: "catalog-select-dropdown-input", brand: "brand-select-dropdown-input",
    condition: "category-condition-single-list-input", price: "price-input--input", save: "upload-form-save-button",
  };
  const PARCEL_TID = { small: "1-package-size--cell", medium: "2-package-size--cell", large: "3-package-size--cell" };
  const BLOCK_URL = ["/member/login", "/member/signup", "/member/general/login", "/session", "/signup"];
  const BLOCK_TEXT = ["captcha", "verify you are human", "are you a robot", "unusual activity", "access denied", "datadome",
    "log in to continue", "log in or sign up"];
  const NOT_FOUND_TEXT = ["pagina niet gevonden", "page not found"];
  const ITEM_HREF = "a[href*='/items/']";

  class Guard extends Error { constructor(m) { super(m); this.name = "Guard"; } }
  class Mismatch extends Guard { constructor(m) { super(m); this.name = "Mismatch"; } }

  function centsToEuros(c) { return `${Math.floor(c / 100)}.${String(c % 100).padStart(2, "0")}`; }

  function parseCents(shown) {
    const m = /\d[\d.,]*/.exec(shown || "");
    if (!m) return null;
    let s = m[0].replace(/[.,]+$/, "");
    if (s.includes(",") && s.includes(".")) {
      s = s.lastIndexOf(",") > s.lastIndexOf(".") ? s.replace(/\./g, "").replace(",", ".") : s.replace(/,/g, "");
    } else s = s.replace(",", ".");
    const n = Math.round(parseFloat(s) * 100);
    return Number.isFinite(n) ? n : null;
  }

  const norm = (s) => String(s).replace(/\r\n/g, "\n").trim().split("\n").map((l) => l.trimEnd()).join("\n");
  const bodyText = (doc) => (doc.body && (doc.body.innerText ?? doc.body.textContent)) || "";
  const el = (doc, tid) => doc.querySelector(`[data-testid='${tid}']`);

  /** Throw Guard on login, CAPTCHA / bot check, 404 or any open dialog. env = {doc, path()} */
  function checkPage(env) {
    const path = env.path().toLowerCase();
    if (BLOCK_URL.some((b) => path.startsWith(b) || path.includes(b))) throw new Guard(`login or session page (${path})`);
    const low = bodyText(env.doc).toLowerCase();
    for (const w of BLOCK_TEXT) if (low.includes(w)) throw new Guard(`blocking page text: '${w}'`);
    for (const w of NOT_FOUND_TEXT) if (low.includes(w)) throw new Guard("page not found (404)");
    if (env.doc.querySelector("[role=dialog]:not([aria-hidden=true]), dialog[open]")) throw new Guard("unexpected dialog open");
  }

  function readValue(doc, tid) {
    const e = el(doc, tid);
    if (!e) return "";
    return "value" in e && e.tagName !== "BUTTON" && e.tagName !== "LI" ? e.value : (e.innerText ?? e.textContent ?? "").trim();
  }

  /** Set an input's value the way a user typing does, so React sees it (native setter + input events). */
  function setNative(e, v) {
    const proto = e.tagName === "TEXTAREA" ? e.ownerDocument.defaultView.HTMLTextAreaElement.prototype : e.ownerDocument.defaultView.HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value").set.call(e, v);
    e.dispatchEvent(new e.ownerDocument.defaultView.Event("input", { bubbles: true }));
  }

  async function typeInto(env, tid, value) {
    const e = el(env.doc, tid);
    if (!e) throw new Guard(`field missing: ${tid}`);
    e.focus();
    setNative(e, "");
    let cur = "";
    for (let i = 0; i < value.length; i += 4) {          // small chunks with a tiny delay, like fast typing
      cur += value.slice(i, i + 4);
      setNative(e, cur);
      if (env.tick) await env.tick();
    }
    e.dispatchEvent(new e.ownerDocument.defaultView.Event("change", { bubbles: true }));
    e.blur();
  }

  function clickTid(env, tid) {
    const e = el(env.doc, tid);
    if (!e) throw new Guard(`control missing: ${tid}`);
    e.click();
  }

  /** Click the option whose own text is exactly `text`. False when absent. */
  function clickOption(doc, text) {
    const want = text.trim().toLowerCase();
    const hits = [...doc.body.querySelectorAll("*")].filter((n) => !n.children.length && n.textContent.trim().toLowerCase() === want);
    if (!hits.length) return false;
    hits[0].click();
    return true;
  }

  /** files = [{name, type, bytes: Uint8Array}] -> add-photos input via DataTransfer. */
  function setPhotos(env, files) {
    const input = el(env.doc, TID.photos);
    if (!input) throw new Guard("photo input missing");
    const w = env.doc.defaultView;
    const dt = new w.DataTransfer();
    for (const f of files) dt.items.add(new w.File([f.bytes], f.name, { type: f.type || "image/jpeg" }));
    input.files = dt.files;
    input.dispatchEvent(new w.Event("change", { bubbles: true }));
  }

  function readBack(doc, p, create) {
    if (readValue(doc, TID.title).trim() !== p.title.trim()) throw new Mismatch("title differs after typing");
    if (norm(readValue(doc, TID.description)) !== norm(p.description)) throw new Mismatch("description differs after typing");
    if (parseCents(readValue(doc, TID.price)) !== p.price) throw new Mismatch("price differs after typing");
    if (create && !readValue(doc, TID.condition).toLowerCase().includes(p.condition.toLowerCase())) throw new Mismatch("condition differs");
  }

  /** Fill the open create/edit page from the claimed queue entry d. env = {doc, path(), pause(sec?), tick(), loadPhotos(d)} */
  async function fillForm(env, d) {
    const p = d.payload, create = d.mode === "create";
    checkPage(env);
    if (create && d.files && d.files.length) {
      setPhotos(env, await env.loadPhotos(d));
      await env.pause(2.0);
      checkPage(env);
    }
    await typeInto(env, TID.title, p.title);
    await env.pause();
    await typeInto(env, TID.description, p.description);
    await env.pause();
    checkPage(env);
    if (create) {
      await env.pause(1.5);                                // Vinted auto-fills category + brand from the title
      for (const [key, want] of [["category", "single trading cards"], ["brand", "pok"]]) {
        if (!readValue(env.doc, TID[key]).toLowerCase().includes(want)) throw new Guard(`${key} not auto-filled as expected`);
      }
      clickTid(env, TID.condition);
      await env.pause();
      if (!clickOption(env.doc, p.condition)) throw new Guard(`condition option '${p.condition}' not found`);
      await env.pause();
      checkPage(env);                                      // 'Item must be unused' dialog lands here
      clickTid(env, PARCEL_TID[p.parcel]);
      await env.pause();
    }
    await typeInto(env, TID.price, centsToEuros(p.price));
    await env.pause();
    checkPage(env);
    readBack(env.doc, p, create);
  }

  /** On the member profile page: href of the item card matching the title (or null). */
  function findItemLink(doc, title) {
    const head = title.slice(0, 25).toLowerCase();
    for (const a of doc.querySelectorAll(ITEM_HREF)) {
      const t = (a.getAttribute("title") || a.innerText || a.textContent || "").trim().toLowerCase();
      if (t && (t.startsWith(head) || t.includes(head))) return a.href;
    }
    return null;
  }

  const api = { TID, PARCEL_TID, ITEM_HREF, Guard, Mismatch, centsToEuros, parseCents, checkPage, readValue, typeInto, clickOption,
    setPhotos, readBack, fillForm, findItemLink };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.MocRecipe = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
