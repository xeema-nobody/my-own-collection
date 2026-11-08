# my-own-collection — roadmap

**Created:** 2026-11-05 · **Last updated:** 2026-11-06
**How to use:** give this file to the project's Claude agent. Work one step at a time, in order. When a step is done (or changes), tick it, add a line to the **Progress log** at the bottom, and bring the update back to socio so this copy stays current.

Functional descriptions only — no technical design. The project agent decides _how_.

**Status legend:** `[ ]` not started · `[~]` in progress · `[x]` done

---

## Why this order

1. **Phase 1 (steps 1–4)** fixes daily friction in what already exists. Cheap, high value, and everything later (scanning many cards, selling) makes it worse if the collection list and price refresh stay slow/manual.
2. **Phase 2 (step 5)** is the big intake unlock — scanning. Collection will grow fast after it.
3. **Phase 3 (step 6)** turns the collection into cash: photos + selling tracker.
4. **Phase 4 (step 7)** sealed products — new asset type, and the source of pulls.
5. **Phase 5 (step 8)** deck/bulk products — needs a large, well-identified collection, so last.

---

# Phase 1 — Fix daily friction

## Step 1 — Bulk price refresh for the whole collection `[x]`

**Problem:** scraped prices only fetchable card by card from the card page.

**Wanted:**

- One button ("Fetch all prices") that fetches scraped prices for every card in the collection, from the Dashboard, Collection page and Settings → Prices.
- Runs in the background; user can leave the page. Visible progress: "42 / 120 done, 3 failed, ~6 min left".
- Can pause/cancel. Safe to re-run: resumes, doesn't redo what just succeeded.
- Prioritisation options: all / only never-fetched / only stale (older than N days) / only most valuable first / only selected stack.
- Politeness built in: spaced-out requests so the three sites don't block or ban. Slow is fine; blocked is not.
- Failures listed clearly (card, source, reason: "no match", "blocked", "layout changed") with one-click retry, and a link to the card's match picker for "no match".
- Finishes with a summary ("118 updated, 2 need attention") and a macOS notification, consistent with existing alerts.
- Feeds the existing data-quality card (how many cards have fresh prices).

**Done when:** one click refreshes the 16-stack collection (and a 500-stack one) without babysitting, and failures are understandable.

## Step 2 — Bulk price refresh for the wishlist `[x]`

**Wanted:**

- Same "Fetch all prices" behaviour, on the Wishlist page.
- Manual by default (button); also included as an option in the existing scheduler once that is switched on.
- Wishlist target-price alerts re-evaluate right after a refresh, so "below target" notifications fire without waiting.
- Option to refresh collection + wishlist together in a single run, with the collection first.

**Done when:** wishlist prices refresh in one click and target alerts fire from fresh data.

## Step 3 — Edit purchase value (and how it was acquired) `[x]`

**Problem:** cost can't be changed after adding a card; some cards were bought, some were just pulled.

**Wanted:**

- Edit cost on any stack/copy after creation.
- Acquisition type per stack/copy: **Purchased**, **Pulled** (cost 0, or optionally an allocated share of the sealed product — see step 7), **Traded**, **Gift**, **Other**.
- Fields: price paid, currency, date, where bought (free text, e.g. "Cardmarket", "local shop"), notes.
- Stack with mixed costs (e.g. 3 copies, bought at different prices): can record per-copy cost, or show an average — pick the simplest that keeps P/L correct.
- Bulk edit: select several stacks → set acquisition type / date / source at once.
- P/L and dashboard treat "Pulled" distinctly: show P/L both with and without pulled cards, so profit isn't flattering or misleading.
- Existing 16 stacks: easy way to fix their cost retroactively.
- Editing is logged (previous value kept) so a mistaken edit is recoverable.

**Done when:** every card in the collection has a correct, editable cost and acquisition type, and P/L reflects it.

## Step 4 — Collection list: pagination, filters, speed `[x]`

**Wanted:**

- **Pagination** (or infinite scroll) with page size choice. Must stay fast at 5,000+ stacks.
- **Filters:** set, rarity, type, language, condition, raw/graded, grader, grade, acquisition type, price range, P/L positive/negative, "needs price", "price stale", on-sale/listed (after step 6), has photos (after step 6).
- **Search** within the collection by name/number.
- **Sort:** value, cost, P/L, name, set, date added, last price update.
- **Views:** table and image grid; choice remembered.
- **Saved filter presets** ("graded only", "cheap bulk < €1", "needs attention").
- Filter state in the page address so back-button and bookmarks work.
- **Speed/caching:** returning to the collection is instant; the list doesn't refetch everything each visit; stale data refreshes quietly in the background. Totals (count, value, P/L) shown for the _filtered_ set.
- Same treatment for the Wishlist list (lighter).

**Done when:** a large synthetic collection (e.g. 5,000 stacks) pages, filters and sorts with no visible waiting.

### 4b. Bulk actions on selected stacks `[x]` built 2026-11-07 (user request same day; awaiting the user's test)

Row checkboxes and "Select all on this page" already exist, but the only bulk action is "Edit cost & type". Wanted on the same selection bar:
- **Fetch prices for the selected stacks only** (so a few new cards do not trigger a fetch of the whole collection). The fetch API already takes a `cards` list (`POST /api/admin/prices/fetch`), so this is mostly a UI action that reuses `usePriceFetchJob` / `BulkFetch` progress.
- **Remove the selected stacks** with a confirm that shows the count and total copies; goes through the same exit history as the single-stack "Sell / remove" (reason removed / gifted / sold, one reason for all), so nothing is silently deleted. A bulk endpoint with one transaction-like pass (per-stack result, partial failures reported).
- Same selection bar on the Wishlist page (fetch prices, remove).
- Select across pages ("select all N matching the filter"), with the count shown before any destructive action.

**Built:** selection bar on Collection and Wishlist has "Fetch prices" (`POST /api/admin/prices/fetch {cards}` with the distinct cards of the picked rows, disabled while a fetch runs; progress in the existing box) and "Remove" (drawer with count + total copies, one reason, per-entry result; `POST /api/collection/bulk-remove` writes one `collection_exits` row per stack, `POST /api/wishlist/bulk-remove` also deletes the entries' alerts; a bad id is reported and the rest still go through). Selection survives page changes on the Collection. Not built: "select all N matching the filter" across pages, sale price per stack in bulk (use Sell / remove).

**Done when:** pick 3 stacks, tap "Fetch prices" and only those 3 cards are fetched; pick 5, remove them with one confirm and see them in Settings > Data > exits.

---

# Phase 2 — Intake by camera

## Step 5 — Scan cards with the phone camera `[~]`

**Goal:** add a card to the collection in a few seconds by pointing the phone at it. "Super easy" is the acceptance bar.

### 5a. Getting the phone connected

- On laptop/desktop browser, an "Add by scanning" button shows a **QR code**. Scanning it with the phone opens the scan screen on the phone, already linked to the user's own collection — no login, no typing.
- On the phone, the scan screen can also be added to the home screen and opened directly later.
- Laptop and phone stay in sync: card added on the phone appears on the laptop immediately (a small "added: Charizard, Base Set" confirmation).
- If the link/QR is no longer valid or the phone is on another network, the screen says what's wrong in plain words.
- **Decision needed first (see Decisions D1):** phone browsers only allow camera use on secure connections. This is the point where "does it ever leave localhost?" gets answered at least for the home network.

### 5b. Identify the card

Order of attempts, most forgiving first:

1. **Name** — read the card name from the photo.
2. **Number + set** — read the collector number (e.g. 4/102) and set symbol/code to narrow.
3. **Whole-card image match** as a helper when text is unreadable (glare, foil, other language).

- Live camera view with a framing guide; auto-captures when steady and in focus, or tap to capture.
- Works in poor light/foil glare as well as it can; tells the user "move closer / less glare" rather than failing silently.
- Manual fallback always one tap away: type the name, or pick from search.
- Languages: at least English and Dutch first; others later (ties to open question on other TCGs).

### 5c. Choose the exact version

- Never auto-add on a guess. After identifying, show **all plausible matches** side by side as images with set, number, rarity, year, language and current price — e.g. Charizard: Base Set, Base Set 1st Edition, Base Set Shadowless, Base Set 2, Evolutions, reprints/promos.
- Most likely match first, with a confidence hint; user taps the right one.
- Edition/variant markers (1st Edition stamp, Shadowless, reverse holo, holo, promo stamp) are highlighted in the comparison, because that's what separates a €5 card from a €5,000 one.
- "None of these" → refine search or add as a manual entry.

### 5d. Capture details

- After picking: set **condition** (NM / LP / MP / HP / DMG — with a short visual guide), **language**, **quantity**, and **acquisition** (purchased / pulled / cost — from step 3; remember the last choice).
- **Batch mode:** after adding, camera is immediately ready for the next card; session shows a running list ("12 added this session"), with undo on the last one and a review screen at the end.
- Duplicates: scanning a card already owned offers "add copy to existing stack" by default.
- Option to **take the intake photos at the same time** and keep them with the card (feeds step 6).

### 5e. Slabs (graded cards)

- Detect that the item is a slab and **read the label**: grader (**PSA, BGS, CGC, ACE**, others), grade and **cert number**.
- Pre-fill grader, grade, cert and the card identity from the label; user confirms.
- Unknown grader → **"Other slab"** option: pick "Other", type grader name + grade manually.
- Cert number kept for later verification and for selling listings.
- A slab whose price isn't known stays flagged "needs price" (existing rule), never valued at raw price.

### Suggested slicing (ship in this order)

1. 5a + 5b-name + 5c + 5d (single card, raw) — usable end to end. **`[x]` built 2026-11-05; real-phone timing (< 15 s) and OCR accuracy on real photos still to be checked by the user.**
   - **1b. Real-photo OCR calibration `[x]` built 2026-11-07.** Cause confirmed: the old reader cropped the top 20 % of the *photo*, and in a real phone photo that is table (the card sits in the middle, about 45 % of the width). Measured on 15 real photos (5 cards x 3, `tests/private/scan_samples/`): **3/15 (20 %) before, 14/15 (93 %) after.** Fix: find the card (Otsu threshold on a thumbnail, box of the lit area), read its top band, then a tight name strip, then binarized crops (names over busy art), then the whole card, then the whole image, stopping at the first confident exact name; ignore "Evolves from X"; a matched base name also offers its ex/V forms (the ex glyph is rarely read). The live view already crops to the framing guide; the Photo button (phone camera app) is the case that needed detection. The type-a-few-letters search was already in the picker and on the camera step. Open: IMG_2994 (Chandelure, glare on the sleeve) still misses; the picker lets the user type.
   - **1c. Find the card as a rectangle, read name + number + set, match prints `[x]` built 2026-11-07, awaiting the user's phone test.** `providers/ocr/cardgeom.py` (OpenCV) finds the card as a 63:88 quadrilateral (edge + brightness contours, any tilt/size/table colour, rejects cut-off cards) and warps it flat to 630x880; the name stages run on the flat card first (then with a 5 % inset for sleeves, then the old brightness stages as fallback). Fixed regions of the flat card give the collector number (digits only, many reads vote), printed total, set code and HP. `services/scan.py` ranks every print by how many signals agree (name, number, printed total, set code) and the picker shows them ("name + number + printed total"); nothing is dropped and nothing is added without a tap. Measured on the 15 real photos: name 14/15 -> 15/15; number read 14/15; top print correct and alone on its signal count 14/15 (name-only gave 756 prints over 15 photos, 12-171 per photo). Miss: IMG_2994 (sleeve glare), falls back to the name list. Set code needs `ptcgo_code`, stored on new imports only (re-import a set to backfill).
2. 5b-number/set + batch mode. *(2026-11-07 calibration on 24 new photos of cards in Vault-X sleeves, many held sideways: the card quad was the whole sleeve and sideways cards came out upside down. Fix: read the inner card quad inside the flat sleeve, try each flat both ways up, run name and number reads in parallel. Names 24/39 -> 38/39, number read on sleeved cards 0/24 -> ~11/24 (wrong reads rank nothing, they just add no signal). Sleeved worst case 6-17 s (was instant-fail), bare card 2 s. Not handled: binder pages (many cards in one photo) and slabs, which belong to slice 3 / 5e.)* **`[x]` built 2026-11-07, awaiting the user's phone test.** Laptop "Start a scan" session (phone polls), typed number + set lookup, batch mode with running count, undo last (also on the single-card done screen) and review. Also: sell / gift / remove cards with history (outside Step 5, requested the same day). Open: slabs (slice 3); re-importing owned sets for `ptcgo_code` is optional (name + number + printed total is the main match, set symbol matching rejected, see decisions.md).
3. 5e slabs. **`[~]` built 2026-11-07 as an assisted flow; detection fix 2026-11-07, awaiting a live slab test on the laptop camera / phone.** First user test: slabs always came back as the raw card. Fix: Scan raw | Scan slab toggle (remembered), taller slab guide, label always read in slab mode, visible "Looks like a slab: switch to slab" prompt in raw mode (`detected`), see decisions.md "Slab mode toggle". Measured on the 24 private slab photos (2 Japanese): label 14 -> 17, grader 13 -> 14-15, grade 7 -> 6-8, cert 13 -> 12-14, name 16 -> 12 on the tight crop (full photo keeps 16), 32 s -> 15-23 s; the guide-crop theory was not confirmed on these photos. Grade and cert read stay weak. `providers/ocr/slab.py` + `slabfields.py` read the label in overlapping tiles (tier word MINT / GEM MINT marks it, cert digit run, grade glyph read again next to the tier word, grader guessed from cert length / subgrade words because labels print a logo). Phone: "This is a slab" switch before the photo, or auto when the card was not an exact hit; the add sheet has Raw | Slab, grader chips (PSA BGS CGC ACE SGC Other), grade (half steps), cert, and the grader name for Other. Same cert scanned twice = no change (`duplicate`). **Measured on the 24 private slab photos (8 slabs, ~7-10 s each): label found 13/24, cert 11/24, grade 5/24, grader 11/24; no CGC slab in the samples.** So the label read is a head start, the user confirms or types; improving it is open (a tight label crop from the phone would read far better).
4. **Scan accuracy pass `[~]` (user feedback 2026-11-07; first pass done 2026-11-07, more open).** *First pass result (42 raw photos, `tests/private/measure_accuracy.py`): right print top-1 14 -> 19, top-3 15 -> 21, in the list 35 -> 36, name in list 38 -> 39, number read 16 (14 right) -> 27 (20 right). Cause of the weak sleeved result: the inner-card quad is flaky inside a sleeve, so the number was read on 1 of 27 sleeved photos; a fixed sleeve crop (3 vertical shifts) now reads it on ~9 more. Ranking now weights signals (number 4, printed total 3, set 3, HP 1, name 1), HP is a new signal, a printed total no catalog card carries is dropped. Still open: sleeved cards where the card sits off the fixed box (Lugia, Charmeleon, Salamence, Celebi, Charizard x2), IMG_2994 glare, Typhlosion name read, Sneasel IMG_3033 name; Sprigatito MEP 061 is not in the catalog at all.)* *Pass 2 (2026-11-08, same 42 photos): top-1 19 -> 23, top-3 21 -> 26, in the list 36 -> 38, name 39 -> 41, number read 27 -> 31 (correct 20 -> 25). `cardgeom.locate_card` finds the card inside the flat sleeve (63:88 box scored by edge strength on its four sides, size prior toward the larger box) and is the first sleeve crop, the fixed boxes stay as fallback; "Ethan's"-style owner prefixes are variants of the bare name; a number read backed by one vote only cannot mark `exact` (set or HP can vouch for it). Every `exact` in the sample set is now the right print. Still open: tiny / glared number lines (Lugia e-card 149/147 which prints higher than the read regions, Charizard 4/102, Salamence 3048, Charmeleon 3043), promo numbers with letters (Celebi XY93), IMG_2994 glare (374 vs 137), IMG_3033 Sneasel name, Sprigatito MEP 061 (data gap: set missing from the catalog, not chased).)* Original note: Current raw baseline (42 photos): name read 35/42, number read 14/15; misses IMG_2994 (374 vs 137), IMG_3033 sneasel, IMG_3046-3048 salamence ex, IMG_3052-3054 Ethan's Typhlosion (sleeved, sideways). Raw scans work: the right print is in the candidate list, but not always first (example: a Snorlax whose print was somewhere down the list). Wanted: rank the right print higher (more signals, better number/total reads, owned sets first), then run the whole `tests/private/scan_samples` set (raw labels.json 39 photos, labels_slabs.json 24 photos) and fix the misses one by one, reporting hit rate and top-1 / top-3 rank, not only "in the list".
5. Image-match fallback, extra languages. *(Japanese cards: 2 of the 8 private slabs are Japanese (Slowking 199, Charizard V 153, no printed total); the catalog is English only, so they cannot match yet. Later, with the language decision D4.)*

**Done when:** from a cold start, scanning and adding a raw card with condition takes < 15 seconds on the phone, and ambiguous cards (Base Set Charizard) always show the version choices.

---

# Phase 3 — Turn the collection into cash

## Step 6 — Photos, listings tracker and selling `[ ]`

### 6a. Photos on my cards `[ ]`

- Attach photos to any stack/copy: front, back, corners/surface close-ups, slab front/back. A guided capture flow from the phone ("front → back → corners") so listing photos are consistent.
- Photos belong to a _specific copy_ (a PSA 9 and a raw copy of the same card have different photos).
- Mark one as the cover photo; reorder; delete; replace.
- Photos stay on the user's own machine (no cloud) and are included in backup/export.

### 6b. Mark cards for sale and track their status `[ ]`

- Each copy has a sale status: **Not for sale → Ready to list → Listed → Sold** (also: Reserved, Withdrawn).
- "Listed" records **where**: Vinted, Cardmarket, eBay, Marktplaats, other — a copy can be listed in more than one place at once.
- Per listing: asking price, listing date, link, notes, shipping cost assumed.
- **Sold:** record sale price, date, platform, fees and shipping paid → app computes **realised profit** vs. cost. Sold copies leave the active collection value but stay in history (realised P/L, sales report).
- When a copy sells on one platform, it's flagged to delist from the others.
- Views: "Ready to list", "Listed (by platform)", "Sold" with totals — € listed, € sold, realised profit, average days to sell.
- Dashboard shows listed value separately from unlisted.

### 6c. Export for listing `[ ]`

- Select copies → export a **listing pack**: title, description text (card, set, number, language, condition, edition, cert for slabs), suggested price, photos, in a ready-to-paste form per platform. Platform formats differ (Vinted title/limits, Cardmarket bulk-upload sheet) — start with the 2 the founder uses most.
- Suggested price from market data with a choice of strategy (match market / slightly under / floor price), always editable.
- After export, offer to mark them "Listed" with the platform and date.

### 6d. Price sync with platforms `[ ]` _(stretch — high value, uncertain feasibility)_

- Goal: keep asking prices of listed items aligned with market. Minimum useful version, no integration needed: a **"Reprice suggestions"** view — listed items whose market price moved > X% since listing, with "suggested new price" and a one-tap "I've updated it" confirmation.
- Full integration only where a platform genuinely allows it. **Must be researched before committing** (Decisions D3): Vinted has no public seller API; Cardmarket's API access is restricted and needs approval; eBay has an official API. Do not build anything that violates a platform's terms or risks the founder's seller account.
- Alert: "listed price is X% below/above market".

**Done when:** a card can go from scanned → photographed → exported → listed → sold with realised profit, entirely tracked in-app.

---

# Phase 4 — Sealed products

## Step 7 — Sealed products and openings `[ ]`

**Wanted:**

- New section **Products** for sealed items: booster box, booster bundle, ETB, booster pack, tin, collection box, blister, etc. Fields: name, set, type, language, quantity, purchase price/date/where, photos, notes.
- Status per unit: **Sealed** (kept) / **Opened** / **Sold sealed**.
- Sealed items have a **market value** (fetched like card prices where a source exists, else manual) and count toward collection value, shown separately from cards.
- **Open a product:** one flow "I opened this" → mark opened (date) → register what came out:
  - add pulled cards using the scanner from step 5 (or search), each linked back to that product,
  - include promos / extras (promo card, coins, code card, sleeves, etc.) — non-card extras logged as notes/items without a value,
  - pulled cards default to acquisition = "Pulled" with an **optional cost allocation** (spread the product price across pulls by value, or leave at 0 — user picks the method).
- **Opening result report** per product: cost vs. value of what was pulled, best hit, hit rate. Across products: "am I net positive opening sealed vs. keeping it sealed vs. selling it sealed?" — the real business question.
- Sealed products can also be tracked in the selling workflow (step 6): listed / sold sealed.
- Dashboard: sealed value, opened-product ROI.

**Done when:** a booster box can be bought, partly opened pack by pack, with pulls attached, and its ROI seen.

---

# Phase 5 — Decks and bulk products

## Step 8 — Deck builder from selected collection cards `[ ]`

_Future — start only after the collection is large and scanning (step 5) works well. Each sub-step is shippable alone._

### 8a. Choose the pool `[ ]`

- Only cards explicitly **marked "available for decks"** enter the pool; the rest of the collection is never touched.
- Quick-mark rules: all cards cheaper than €1 / €2 / €5 (user-adjustable), by set, by type, by rarity; excludes graded, listed-for-sale and high-value cards by default.
- Pool view with counts and total value, so "I'm giving up €37 of bulk" is visible before committing.

### 8b. Build a deck `[ ]`

- Choose the game/format (Pokémon first), target **difficulty** (beginner / intermediate / advanced) and **power level** (casual / mid / strong), and the theme (a type, an evolution line, a mechanic).
- App proposes decks from the pool and shows **cohesion**: do the cards work together under the game's rules (legal count, enough Pokémon / energy / trainers, evolution lines complete, energy types matching, a clear strategy, no dead cards). Plain-language verdict: "Playable, beginner-friendly, 3 weak slots, missing a Stage 1".
- Manual editing: swap cards in/out, see cohesion update live; "what's missing" list, possibly pointing to the wishlist or to cheap buys.
- Several candidate decks can share the pool; the app warns when two decks want the same single copy.

### 8c. Turn a deck into a product `[ ]`

- "Create deck" **groups the chosen cards into one new Product** (type: Deck) with name, difficulty, power level, photo, cost basis (sum of the cards' cost) and market value.
- Those cards are **moved out of the collection** into the deck product (still traceable; "dissolve deck" returns them).
- Deck products flow into the selling workflow (step 6): list, price, sold, realised profit — including "this bulk made €X as a deck vs. as loose bulk".
- Dashboard reflects the move: collection value drops by what moved, deck inventory value appears separately.

**Done when:** €1-and-under bulk can be turned into a playable, labelled, priced deck product and sold, with the collection updated.

---

# Decisions to take (blocking marked)

| #   | Decision                                                                 | Blocks                   | Notes                                                                                                                                                                     |
| --- | ------------------------------------------------------------------------ | ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| D1  | **ANSWERED 2026-11-05: Tailscale** (private tailnet, no LAN exposure, no CA install; see decisions.md). Was: home-network only, or reachable from anywhere? | Step 5                   | Camera needs a secure connection on the phone. Home-network-only keeps "no cloud, no auth worry"; anywhere triggers auth/hardening. Recommend: home network only for now. |
| D2  | Which marketplaces matter first (Vinted, Cardmarket, eBay, Marktplaats)? | Step 6c                  | Pick the top 2 for export formats.                                                                                                                                        |
| D3  | Marketplace price sync: research feasibility/terms before any build      | Step 6d                  | Don't risk seller accounts. Start with reprice suggestions.                                                                                                               |
| D4  | Other TCGs after Pokémon — which, and catalog source each                | Step 5 languages/catalog | Affects scan identification too.                                                                                                                                          |
| D5  | Switch on scheduler + backup schedule now?                               | Step 1–2                 | Backups matter more once photos and sales history exist. Recommend: install backup schedule before step 6.                                                                |
| D6  | Switch to TCGdex before pokemontcg.io keys end (2027-03-01)              | —                        | Hard deadline. Do not leave until Feb 2027.                                                                                                                               |
| D7  | Scan accuracy bar: is "pick from candidates" acceptable for every scan?  | Step 5                   | Assumed yes (never auto-add).                                                                                                                                             |
| D8  | Cost allocation method for pulled cards                                  | Step 7                   | Default 0 vs. spread by value.                                                                                                                                            |

# Risks

- **Scrapers break** when a site changes layout; bulk fetch (step 1) will surface this faster and louder. Show per-source health on the dashboard. Paid/official price API remains an open option.
- **Bulk scraping gets blocked** (Cloudflare/rate limits). Keep pacing conservative; slow completion is acceptable.
- **Scan misidentifies a variant** (1st edition vs. unlimited) → wrong value. Mitigated by never auto-adding and highlighting variant markers.
- **Marketplace terms.** Automating Vinted/Cardmarket may violate terms. Stay with export + tracking unless an official route exists.
- **Photos grow backups and disk.** Plan storage/backup before step 6a.
- **Single user, no auth + phone access** = exposure if it leaves the home network (D1).

# Progress log

| Date       | Step | Update                                                 |
| ---------- | ---- | ------------------------------------------------------ |
| 2026-11-05 | —    | Roadmap created from founder request. Nothing started. |
| 2026-11-05 | 1    | Done: "Fetch all prices" (all / never / stale / most valuable / stack) on Dashboard, Collection, Settings -> Prices; ETA, pause/resume/cancel, resume-by-skip, failure table + retry + match link, summary + macOS notification, fresh-price counts on data-quality card. Pacing unchanged (sequential, per-site fetcher limits). |
| 2026-11-05 | 2    | Done: "Fetch all prices" on the Wishlist page via a scope picker (Collection / Wishlist / Both, collection first, deduped) in the shared BulkFetch; alerts re-evaluated right after a run (wishlist target alerts fire at once, wishlist-only run writes no snapshot); scheduler option `SCHEDULER_FETCH_WISHLIST`; wishlist freshness counts on the Wishlist page and data-quality card. Same sequential pacing. |
| 2026-11-05 | 3    | Done: acquisition type (Purchased/Pulled/Traded/Gift/Other) + price per copy/currency/date/where bought editable per stack (Collection details drawer, card page pencil, add form) and in bulk (row checkboxes); weighted average on merge; edit log with restore; P/L now only over stacks with a cost, plus P/L excl. pulled on Collection and Dashboard; filters Acquired how / No cost to fix the old stacks; export/import carry the type (CSV `acquired_type`). Per-copy lots not built (one type + average per stack). |
| 2026-11-05 | 4    | Done: server-side filter / sort / paging over a cached whole-collection valuation (warm list query 5-15 ms at 5,000 synthetic stacks, 10-34 ms at 10,000; cold build ~0.4-0.8 s once per change). New filters: set, rarity, card type, grader, grade, price per copy range, P/L positive/negative, price stale (plus existing); sorts: name, set, date added, last price update (plus value, cost, P/L, qty); totals for the filtered set; table | image grid (remembered); saved presets in Mongo + built-ins; URL state; quiet background refresh. Wishlist: search, sort, presets, grid. On-sale and has-photos filters wait for Step 6. |
| 2026-11-05 | 5 | Slice 1 built (5a + 5b-name + 5c + 5d): `/scan` phone page (live camera with guide or native camera capture), local Tesseract name reading, version picker with set/number/rarity/year/variants/price/owned and edition warning for 1st Edition / Shadowless sets, condition/language/copies/cost with remembered last choice, duplicate joins existing stack, laptop "Added: ..." toast + refresh, QR panel on Collection. Phone reaches the app over Tailscale through a Caddy gate that only passes 4 scan endpoints (D1). Not done: slices 2-4, undo, real-photo accuracy measurement, iPhone/Chrome/Add-to-Home-Screen checks. |
| 2026-11-07 | 5 | Sub-step 1c built: card found as a rectangle and warped flat (OpenCV headless added), number / printed total / set code / HP read from fixed regions, prints ranked by agreeing signals. Real photos: name 15/15, number 14/15, exactly-one-print 14/15. New photos (light table, tilt, glare, old cards, toploader) still to be added by the user. |
| 2026-11-07 | 5 | Sub-step 1b done: real-photo OCR measured (3/15 -> 14/15), card detection + staged crops, private accuracy test set (git-ignored). Valuation now treats a blank or 0 acquisition price as "no cost" (not a real cost), so P/L counts only stacks with cost above 0. |
| 2026-11-07 | 5 | Slice 2 built: laptop "Start a scan" session (phone polls `/api/scan/session`, laptop panel shows each card the phone adds), typed number + set lookup, batch mode (running count, undo last within 10 min, review), undo on the single-card screen. Phone gate allowlist +3 calls. Not yet: new real-photo calibration (waiting on the user's photos), phone test of slice 2. |
| 2026-11-07 | — | Sell / gift / remove: "Sell / remove" on a stack (reason, copies, optional sale price, note), history in `collection_exits` with the cost snapshot, list in Settings > Data. Old silent delete now logs too. Realized P/L report is Step 7. |
| 2026-11-06 | 5 | Phone setup done on the user's Mac and iPhone (Tailscale, `lan.sh setup/up`, `tailscale serve`); page opens and asks for camera. First real scan failed to read the name -> new sub-step 1b (real-photo OCR calibration), waiting on the user's sample photos. Slice 1 still uncommitted on `feat/scan-slice1`. The 14 no-cost stacks were filled in by the user (some set to Pulled with no cost; P/L counts only stacks with a cost above 0, by design). |
| 2026-11-07 | 5 | Slice 3 (5e slabs) built as an assisted flow: slab label OCR (`providers/ocr/slab.py`, `slabfields.py`), "This is a slab" switch, Raw / Slab add sheet with grader chips, grade, cert and Other grader name, duplicate cert guard, slab never valued at raw. Label read measured weak on 24 photos (label 13/24, cert 11/24, grade 5/24). **User test the same day: raw scans fine (right print in the list, ranking can improve), slabs not recognised from the laptop page (always the raw card).** Open: reproduce + fix slab detection, scan accuracy pass over all sample photos, Step 4b bulk actions. |
| 2026-11-07 | 4b | Bulk actions built: Collection and Wishlist selection bars get "Fetch prices" (selected stacks' cards only) and "Remove" (confirm with count + copies, one reason, `POST /api/collection/bulk-remove` = one exit row per stack, per-stack results; `POST /api/wishlist/bulk-remove` also drops alerts). Tests: 3 backend, 3 vitest. Slice 3 committed (b01ca34). Not yet done from the same brief: slab detection fix (baseline measure script `tests/private/measure_slab_modes.py`: full photo vs guide crop, switch off/on) and the scan accuracy pass. |
