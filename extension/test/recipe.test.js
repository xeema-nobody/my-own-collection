// @vitest-environment jsdom
import { createRequire } from "node:module";
import { beforeEach, describe, expect, it } from "vitest";

const R = createRequire(import.meta.url)("../recipe.js");

const FORM = (extra = "") => `
  <input type="file" data-testid="add-photos-input">
  <input data-testid="title--input"><textarea data-testid="description--input"></textarea>
  <input data-testid="catalog-select-dropdown-input" value="Single trading cards">
  <input data-testid="brand-select-dropdown-input" value="Pokémon">
  <button data-testid="category-condition-single-list-input">Select</button>
  <ul id="opts" hidden><li><span>Very good</span></li><li><span>New</span></li></ul>
  <div data-testid="1-package-size--cell">small</div>
  <input data-testid="price-input--input">
  <button data-testid="upload-form-save-button">Upload</button>${extra}`;

let path;
const env = (over = {}) => ({ doc: document, path: () => path, pause: async () => {}, tick: async () => {}, loadPhotos: async () => [], ...over });
const item = (over = {}, p = {}) => ({ mode: "create", files: ["01.jpg"], payload: { title: "Charizard - Base 4", description: "Line 1\nLine 2", price: 1500,
  condition: "Very good", parcel: "small", ...p }, ...over });

// jsdom has no DataTransfer / assignable input.files: minimal stand-ins
class DT { constructor() { this.list = []; this.items = { add: (f) => this.list.push(f) }; } get files() { return this.list; } }

beforeEach(() => {
  path = "/items/new";
  window.DataTransfer = DT;
  document.body.innerHTML = FORM();
  Object.defineProperty(document.querySelector("[data-testid='add-photos-input']"), "files", { value: null, writable: true });
  // choosing the condition shows the picked value in the trigger button, as Vinted does
  document.querySelector("#opts").querySelectorAll("span").forEach((s) => s.addEventListener("click", () => {
    document.querySelector("[data-testid='category-condition-single-list-input']").textContent = s.textContent;
  }));
});

describe("money", () => {
  it("cents <-> euros", () => {
    expect(R.centsToEuros(1500)).toBe("15.00");
    expect(R.centsToEuros(5)).toBe("0.05");
    expect(R.centsToEuros(1999)).toBe("19.99");
  });
  it("parses shown prices", () => {
    for (const [s, c] of [["15.00", 1500], ["15,00", 1500], ["€ 1.234,50", 123450], ["1,234.50", 123450], ["0,05", 5]]) expect(R.parseCents(s)).toBe(c);
    expect(R.parseCents("")).toBeNull();
    expect(R.parseCents("abc")).toBeNull();
  });
});

describe("guards", () => {
  it.each(["/member/login", "/session", "/member/signup"])("login url %s", (p) => {
    path = p;
    expect(() => R.checkPage(env())).toThrow(/login or session/);
  });
  it("captcha text", () => {
    document.body.textContent = "Please complete the CAPTCHA";
    expect(() => R.checkPage(env())).toThrow(/captcha/i);
  });
  it("404 page", () => {
    document.body.textContent = "Pagina niet gevonden";
    expect(() => R.checkPage(env())).toThrow(/404/);
  });
  it("expected success dialog is allowed only when named", () => {
    document.body.insertAdjacentHTML("beforeend", `<div role="dialog">Pokémon Very good €1.50 Item listed Fact: uploading more items speeds up sales.</div>`);
    expect(() => R.checkPage(env())).toThrow(/unexpected dialog/);
    expect(() => R.checkPage({ ...env(), allowDialog: ["item listed"] })).not.toThrow();
    document.body.insertAdjacentHTML("beforeend", `<div role="dialog">Item must be unused</div>`);
    expect(() => R.checkPage({ ...env(), allowDialog: ["item listed"] })).toThrow(/Item must be unused/);
  });

  it("open dialog, but not a hidden one", () => {
    document.body.insertAdjacentHTML("beforeend", `<div role="dialog" aria-hidden="true"></div>`);
    expect(() => R.checkPage(env())).not.toThrow();
    document.body.insertAdjacentHTML("beforeend", `<div role="dialog" style="display:none">cookies</div><div style="visibility:hidden"><div role="dialog">x</div></div>`);
    expect(() => R.checkPage(env())).not.toThrow();
    document.body.insertAdjacentHTML("beforeend", `<div role="dialog" data-testid="unused-dlg">Item must be unused</div>`);
    expect(() => R.checkPage(env())).toThrow(/unexpected dialog open: <div testid=unused-dlg> "Item must be unused"/);
  });
  it("clean page passes", () => expect(() => R.checkPage(env())).not.toThrow());
});

describe("fillForm", () => {
  it("create: types fields, picks condition + parcel, reads back", async () => {
    document.querySelector("#opts").hidden = false;
    const clicked = [];
    document.querySelector("[data-testid='1-package-size--cell']").addEventListener("click", () => clicked.push("small"));
    let photos = 0;
    await R.fillForm(env({ loadPhotos: async () => { photos++; return []; }, doc: document }), item()).catch((e) => { throw e; });
    expect(document.querySelector("[data-testid='title--input']").value).toBe("Charizard - Base 4");
    expect(document.querySelector("[data-testid='description--input']").value).toBe("Line 1\nLine 2");
    expect(document.querySelector("[data-testid='price-input--input']").value).toBe("15.00");
    expect(clicked).toEqual(["small"]);
    expect(photos).toBe(1);
  });

  it("typing fires input events React listens to", async () => {
    const seen = [];
    document.querySelector("[data-testid='title--input']").addEventListener("input", (e) => seen.push(e.target.value));
    await R.typeInto(env(), "title--input", "abcdefghij");
    expect(seen.at(-1)).toBe("abcdefghij");
    expect(seen.length).toBeGreaterThan(2);
  });

  it("update mode: title/description/price only", async () => {
    document.querySelector("[data-testid='catalog-select-dropdown-input']").value = "";
    let photos = 0;
    await R.fillForm(env({ loadPhotos: async () => { photos++; return []; } }), item({ mode: "update", files: ["01.jpg"] }));
    expect(photos).toBe(0);
    expect(document.querySelector("[data-testid='price-input--input']").value).toBe("15.00");
    expect(document.querySelector("[data-testid='category-condition-single-list-input']").textContent).toBe("Select");
  });

  it("create guard: category not auto-filled", async () => {
    document.querySelector("[data-testid='catalog-select-dropdown-input']").value = "";
    await expect(R.fillForm(env(), item())).rejects.toThrow(/category not auto-filled/);
  });

  it("create guard: condition option missing", async () => {
    await expect(R.fillForm(env(), item({}, { condition: "Brand new" }))).rejects.toThrow(/condition option/);
  });

  it("guard: dialog appears after picking the condition (slab)", async () => {
    document.querySelector("#opts").hidden = false;
    document.querySelector("#opts span").addEventListener("click", () => document.body.insertAdjacentHTML("beforeend", `<div role="dialog">Item must be unused</div>`));
    await expect(R.fillForm(env(), item())).rejects.toThrow(/dialog/);
  });

  it("guard: login page mid-run", async () => {
    await expect(R.fillForm(env({ path: () => "/member/login" }), item())).rejects.toThrow(/login/);
  });

  it("read-back mismatch is a Guard (price reformatted by the page)", async () => {
    const price = document.querySelector("[data-testid='price-input--input']");
    price.addEventListener("input", () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(price, "99.00"); });
    await expect(R.fillForm(env({ doc: document }), item({ mode: "update" }))).rejects.toBeInstanceOf(R.Mismatch);
  });

  it("missing field is a Guard, not a crash", async () => {
    document.querySelector("[data-testid='title--input']").remove();
    await expect(R.fillForm(env(), item({ mode: "update" }))).rejects.toThrow(/field missing/);
  });
});

describe("photos", () => {
  it("sets files on the input via DataTransfer and fires change", () => {
    const input = document.querySelector("[data-testid='add-photos-input']");
    let changed = 0;
    input.addEventListener("change", () => changed++);
    R.setPhotos(env(), [{ name: "01.jpg", bytes: new Uint8Array([1, 2]) }, { name: "02.jpg", bytes: new Uint8Array([3]) }]);
    expect(input.files.map((f) => f.name)).toEqual(["01.jpg", "02.jpg"]);
    expect(input.files[0].type).toBe("image/jpeg");
    expect(changed).toBe(1);
  });
});

describe("profile page", () => {
  it("finds the uploaded item link by title prefix", () => {
    document.body.innerHTML = `<a href="/items/1-other" title="Pikachu holo">x</a><a href="https://www.vinted.nl/items/99-charizard" title="Charizard - Base 4 - Near Mint, 15 EUR">y</a>`;
    expect(R.findItemLink(document, "Charizard - Base 4 - Near Mint")).toBe("https://www.vinted.nl/items/99-charizard");
    expect(R.findItemLink(document, "Mew ex")).toBeNull();
  });
});
