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

> **Decided 2026-11-10 order: (1) TCGdex-only extras import (DONE 2026-11-10), (2) slab leftovers (label grade, tiny-text fallback), (3) image-match fallback for unread number lines (DONE 2026-11-10), (4) Japanese Pokémon (D4) (BUILT 2026-11-10 incl. the "import this set" prompt on a miss, awaiting the user's import + check; see decisions.md 'Japanese Pokémon').** Earlier note: **Next up (re-prioritised 2026-11-09 after the slice 4 phone check): 5h price scope, 5g coverage audit and the TCGdex extras import are done, then slab slices 5 + 6 (done, see changelog), then the raw accuracy misses (item 4, pass 3 done 2026-11-10; the rest are OCR limits, see item 4).** 5f slices 1-4 are done (the phone result card works; slices 5-6 are polish). Backup schedule done 2026-11-10 (launchd, daily 05:30). 

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

### 5f. Slab identity from the cert, not from the photo `[x]` slices 1-6 done 2026-11-09 (user feedback after the live slab test, 2026-11-08; awaiting a phone check of the faster read)

Live test findings: slab scanning is slow (about 20 s per photo), it shows the *raw-card image match* first although the slab label already names the card, set, number and variant (holo, 1st edition), and the label is read badly enough that the list is often empty or wrong. The label is the identity; the card photo should not be searched at all in slab mode.

- **Read only what a slab needs:** grader (logo / layout) and cert number, plus the tier and grade. No raw-card OCR in slab mode (it is the slow part and shows the wrong list first). Target: read under 3 s, cert lookup under 2 s.
- **Cert lookup per grader:** the cert number opens that grader's public cert page, which gives the exact card (e.g. ACE 158690 = Radiant Charizard 011/078, Pokémon GO, 2022, Holo, grade 10 Gem Mint, subgrades 10/10/10/10, population). The page differs per company (ACE, PSA, Beckett/BGS, CGC, SGC), so a **grader registry** holds, per grader: cert URL template, cert format, how to read it (public page, JSON, API token, not machine-readable) and what fields it returns. Documented in `docs/grading-cert-pages.md`, coded in `providers/grading/`.
- **Always keep the link:** even when a page cannot be read by machine, the slab stores grader + cert, and the collection shows an "Open <grader> report" link built from the template. The fetched details (name, set, number, year, variant, language, grade, subgrades, fetched at) are cached on the slab so it works offline afterwards.
- **Match the catalog from the cert details** (name + number + printed total, set name or year as a bonus, same rule as raw scans) and show that card first, prefilled with grader, grade, cert and variant. Never auto-add. Japanese slabs and sets missing from the catalog show the cert details and let the user pick or type.
- **Fallbacks, in order:** cert read + lookup -> label text (name, number, set printed on the label) against the catalog, no network -> typed name / number -> raw card image match only on request.
- **Cert accuracy matters now:** a wrong cert is a wrong card, so the result screen shows what the cert page returned next to what the label said (grade and name must agree) and the user confirms.
- **Graders verified (slice 1 done 2026-11-09):** ACE plain httpx; PSA + Beckett through the host fetcher (Cloudflare blocks plain requests; pages free in a browser); CGC / SGC link-only until verified. Matching signals differ (ACE total; PSA number only; BGS name + set only). Fetcher sites come from `~/.moc-fetcher/sites.json` (no restart to add a grader); `/health` lists them and the app degrades to link-only with a restart hint. Other graders are added when a slab needs them; unsupported scans are counted.
- Plan: slices in 3d below. Decisions: decisions.md "Slab identity from the cert".

### 5g. Missing cards in the catalog / search `[x]` audit + fixes done 2026-11-09 (TCGdex-only extras imported 2026-11-10, see below)

**Findings 2026-11-09.** (1) Typed `number + set code` (e.g. `228` + `UNM`) returned 0: neither the stored sets nor the cards carried `ptcgo_code` (the upstream sends it for 152 of 177 sets). Fixed: `lookup` / `set_codes` read the code from the `sets` collection, `import_catalog` copies set fields onto the cards (`sync_set_fields`, idempotent, every set gets its code, import targets also name/totals); all 151 coded sets were synced. (2) **Upstream paging bug:** `orderBy=number` is not unique, pages overlap and drop cards (Delta Reign `me6`: 141 rows fetched, 100 unique). Now `orderBy=number,id`. (3) `me6` Delta Reign (released 2026-11-06) was the only set the source lists that we lacked; imported (141 cards). (4) Source totals match stored counts for all 176 older sets (6 sets hold more than the source total: secret rares / extras, normal). (5) Audit: `GET /api/admin/catalog/audit` (one live `list_sets`, no card download; tags `new_at_provider`, `empty`, `short`, `total_changed`, `code_missing`, `over_total`) + Settings > Catalog "Coverage audit" table with "Select gaps". (6) Garchomp & Giratina-GX 228 and Blastoise EX 142 are in the catalog and the typed name finds them; the scan miss was the set-code lookup. **Done 2026-11-10 (`services/catalog_extras.py`, +713 cards, catalog only):** svp +26, swshp +3, sve +8, ecard2 +17 (a/b + H cards TCGdex lists), det1 +1, new sets mep 112 (Sprigatito MEP 061 found by typed `61` + `MEP`), mee 16, mfb 34/48, McDonald's 2023/24, trainer kits (tk-*; tk-sm-l 18/30), fut2020, 30th-c. TCGdex returns no cards for `jumbo` and `rc` (empty set docs stored). Most new promos have no image upstream. Not imported: Pocket sets (A1..B2a, P-A), miscp, wp, sp, ex5.5, exu, xya, cel25c +3, zsv10pt5 +1. **Was open:** the pokemontcg.io source itself lacks cards TCGdex has (svp 200 vs 226, swshp 304 vs 307, sve 16 vs 24, ecard2 182 vs 186, det1 18 vs 19) and whole sets (MEP / MEE Mega Evolution promos + energy, My First Battle, McDonald's 2023/24, trainer kits, Jumbo, Futsal 2020). The "Mew 151 metal card" (UPC box) is in neither source. Decision with the user: which of these to import (schema is Pokémon-English only).

(original note:)

User could not find some cards, e.g. Blastoise EX #142 (XY, 2014). Checked 2026-11-08: the card IS in the catalog (`xy1`, Blastoise-EX 142/146) and the laptop search, the scan type-a-name search and the number lookup all return it on the first page, so it is not a plain data gap. Second report 2026-11-09: Garchomp & Giratina GX #228 (Unified Minds, tag team). Also in the catalog (`sm11-228` "Garchomp & Giratina-GX"; laptop search, scan search with "&" / "GX" / "-GX" and number + set name / id lookup all find it). So both reports are NOT plain data gaps: the failing path is unknown (ask for it). One real bug found: the lookup by printed set code (`number=228&set=UNM`) returns nothing, because the card's embedded `set` has no `ptcgo_code` (probably set-code matching is dead for every card; verify + fix + test). Needs the user's exact path (photo scan? typed name on the phone? which screen?). Then: (1) reproduce per path, (2) a **catalog coverage audit** comparing imported cards per set against the provider's set totals (missing sets, missing cards, promos), (3) fix or re-import, with a test per cause.

### 5h. Price scope: prices only for what the user tracks `[x]` built 2026-11-09 (awaiting user check; see pricing.md "Price scope")

Decided with the user 2026-11-09: untracked cards show "no price (not tracked)" + one-card "Fetch price"; existing untracked price rows are KEPT (no purge, no purge script). Built: `tracked_card_ids`, import writes no prices, refresh scopes tracked / collection / wishlist (daily scheduled run = tracked), fetch targets by set = tracked only, background fetch on add (`PRICE_ON_ADD`), `POST /api/cards/{id}/refresh-price`, UI wording + Fetch price, tests. Original brief follows.

The catalog import writes price rows for every card of every imported set (the pokemontcg.io payload carries them) and `refresh_prices` with scope `all` / `sets` does too, so almost every card in the app has prices and `price_observations` covers the whole catalog. Wanted: prices stored and fetched only for cards in the collection (when the user picks / fetches them) and for wishlist cards (these may refresh automatically about once a day). Everything else shows "no price (not tracked)" and may fetch one card on demand when opened. Slices: decide with the user (on-demand fetch on open; keep or purge existing untracked rows after `scripts/backup.sh`), one `tracked_card_ids` rule (collection + wishlist) used by import / refresh / snapshots / fetch jobs / movers / alerts, import stops writing prices, scheduler refreshes the wishlist daily, UI wording + "Fetch price", tests (import writes no price rows, untracked = `None` never 0, wishlist / collection make a card tracked), docs (pricing.md, decisions.md, architecture.md).

### Suggested slicing (ship in this order)

1. 5a + 5b-name + 5c + 5d (single card, raw) — usable end to end. **`[x]` built 2026-11-05; real-phone timing (< 15 s) and OCR accuracy on real photos still to be checked by the user.**
   - **1b. Real-photo OCR calibration `[x]` built 2026-11-07.** Cause confirmed: the old reader cropped the top 20 % of the *photo*, and in a real phone photo that is table (the card sits in the middle, about 45 % of the width). Measured on 15 real photos (5 cards x 3, `tests/private/scan_samples/`): **3/15 (20 %) before, 14/15 (93 %) after.** Fix: find the card (Otsu threshold on a thumbnail, box of the lit area), read its top band, then a tight name strip, then binarized crops (names over busy art), then the whole card, then the whole image, stopping at the first confident exact name; ignore "Evolves from X"; a matched base name also offers its ex/V forms (the ex glyph is rarely read). The live view already crops to the framing guide; the Photo button (phone camera app) is the case that needed detection. The type-a-few-letters search was already in the picker and on the camera step. Open: IMG_2994 (Chandelure, glare on the sleeve) still misses; the picker lets the user type.
   - **1c. Find the card as a rectangle, read name + number + set, match prints `[x]` built 2026-11-07, awaiting the user's phone test.** `providers/ocr/cardgeom.py` (OpenCV) finds the card as a 63:88 quadrilateral (edge + brightness contours, any tilt/size/table colour, rejects cut-off cards) and warps it flat to 630x880; the name stages run on the flat card first (then with a 5 % inset for sleeves, then the old brightness stages as fallback). Fixed regions of the flat card give the collector number (digits only, many reads vote), printed total, set code and HP. `services/scan.py` ranks every print by how many signals agree (name, number, printed total, set code) and the picker shows them ("name + number + printed total"); nothing is dropped and nothing is added without a tap. Measured on the 15 real photos: name 14/15 -> 15/15; number read 14/15; top print correct and alone on its signal count 14/15 (name-only gave 756 prints over 15 photos, 12-171 per photo). Miss: IMG_2994 (sleeve glare), falls back to the name list. Set code needs `ptcgo_code`, stored on new imports only (re-import a set to backfill).
2. 5b-number/set + batch mode. *(2026-11-07 calibration on 24 new photos of cards in Vault-X sleeves, many held sideways: the card quad was the whole sleeve and sideways cards came out upside down. Fix: read the inner card quad inside the flat sleeve, try each flat both ways up, run name and number reads in parallel. Names 24/39 -> 38/39, number read on sleeved cards 0/24 -> ~11/24 (wrong reads rank nothing, they just add no signal). Sleeved worst case 6-17 s (was instant-fail), bare card 2 s. Not handled: binder pages (many cards in one photo) and slabs, which belong to slice 3 / 5e.)* **`[x]` built 2026-11-07, awaiting the user's phone test.** Laptop "Start a scan" session (phone polls), typed number + set lookup, batch mode with running count, undo last (also on the single-card done screen) and review. Also: sell / gift / remove cards with history (outside Step 5, requested the same day). Open: slabs (slice 3); re-importing owned sets for `ptcgo_code` is optional (name + number + printed total is the main match, set symbol matching rejected, see decisions.md).
3. 5e slabs. **`[~]` built 2026-11-07 as an assisted flow; detection fix 2026-11-07, awaiting a live slab test on the laptop camera / phone.** First user test: slabs always came back as the raw card. Fix: Scan raw | Scan slab toggle (remembered), taller slab guide, label always read in slab mode, visible "Looks like a slab: switch to slab" prompt in raw mode (`detected`), see decisions.md "Slab mode toggle". Measured on the 24 private slab photos (2 Japanese): label 14 -> 17, grader 13 -> 14-15, grade 7 -> 6-8, cert 13 -> 12-14, name 16 -> 12 on the tight crop (full photo keeps 16), 32 s -> 15-23 s; the guide-crop theory was not confirmed on these photos. Grade and cert read stay weak. `providers/ocr/slab.py` + `slabfields.py` read the label in overlapping tiles (tier word MINT / GEM MINT marks it, cert digit run, grade glyph read again next to the tier word, grader guessed from cert length / subgrade words because labels print a logo). Phone: "This is a slab" switch before the photo, or auto when the card was not an exact hit; the add sheet has Raw | Slab, grader chips (PSA BGS CGC ACE SGC Other), grade (half steps), cert, and the grader name for Other. Same cert scanned twice = no change (`duplicate`). **Measured on the 24 private slab photos (8 slabs, ~7-10 s each): label found 13/24, cert 11/24, grade 5/24, grader 11/24; no CGC slab in the samples.** So the label read is a head start, the user confirms or types; improving it is open (a tight label crop from the phone would read far better).
3c. **Slab position reader `[x]` 2026-11-08, uncommitted until the user has seen it.** `slab.find_slab` boxes the slab against the dark table, the label zone is the top 34 % of it, grade read from tight crops by the tier word. 24 slab photos: label 17 -> 21, grader 14 -> 18, grade 6 -> 15, cert 12 -> 17, 22.7 s -> 7.8 s. Superseded as the main path by 5f (cert lookup); stays as the cert/grader reader. See decisions.md "Slab label read by position".
3d. **Slab cert lookup `[~]` TOP PRIORITY, see 5f.** Slices 1 (verify graders), 2 (fetcher sites + `providers/grading/`) and 3 (`services/slab.py`, `GET /api/scan/cert`, identify without raw OCR, `report_url` + `cert_info` on the grading doc) done 2026-11-09. First phone test: ACE + PSA ok; BGS "Gardevoir ex SIR" not matched (page name carries the rarity) and a misread cert (a baseball card) looked up silently. **3b (set-first token matching, rarity signal, `GET /api/scan/certs/recent`) and 3c (`warnings`: grade / tier vs label, non-Pokemon page, cert length) done 2026-11-09 (committed 84b4146). **4 phone result card done 2026-11-09 (`SlabResult`: page summary, warnings, edit grader / cert and look up again, then AddSheet; `Scan.slab.test.tsx`), awaiting the phone check.** **5 speed + 6 cert accuracy done 2026-11-09 as one piece (locate the label, read only it; grader 17 -> 21, cert 12 -> 20, grade 15 -> 12, calls 28.7 -> 18.1, 10.1 s -> 5.1 s; open: label grade and the ~5 tiny-text photos that still fall back to the slow tile read). Leftovers pass 2026-11-10: grade 12 -> 18/24, cert 21, grader 22, tilted labels leveled on retry, see decisions.md 'Slab leftovers'; still open: ACE dark label (white text), 5 grade misses.** 5g (missing cards) is done.
3b. **Raw / slab start buttons `[x]` built 2026-11-08, awaiting the user's live phone check (user request after the live test).** The laptop shows two buttons, "Scan raw cards" and "Scan slabs"; the session carries `mode` and the phone follows a new session id in memory (without overwriting its remembered default); the phone toggle still works mid-session. See decisions.md "Scan session mode". Slab OCR accuracy stays a separate open item.
4. **Scan accuracy pass `[~]` (user feedback 2026-11-07; first pass done 2026-11-07, more open).** *First pass result (42 raw photos, `tests/private/measure_accuracy.py`): right print top-1 14 -> 19, top-3 15 -> 21, in the list 35 -> 36, name in list 38 -> 39, number read 16 (14 right) -> 27 (20 right). Cause of the weak sleeved result: the inner-card quad is flaky inside a sleeve, so the number was read on 1 of 27 sleeved photos; a fixed sleeve crop (3 vertical shifts) now reads it on ~9 more. Ranking now weights signals (number 4, printed total 3, set 3, HP 1, name 1), HP is a new signal, a printed total no catalog card carries is dropped. Still open: sleeved cards where the card sits off the fixed box (Lugia, Charmeleon, Salamence, Celebi, Charizard x2), IMG_2994 glare, Typhlosion name read, Sneasel IMG_3033 name; Sprigatito MEP 061 is not in the catalog at all.)* *Pass 2 (2026-11-08, same 42 photos): top-1 19 -> 23, top-3 21 -> 26, in the list 36 -> 38, name 39 -> 41, number read 27 -> 31 (correct 20 -> 25). `cardgeom.locate_card` finds the card inside the flat sleeve (63:88 box scored by edge strength on its four sides, size prior toward the larger box) and is the first sleeve crop, the fixed boxes stay as fallback; "Ethan's"-style owner prefixes are variants of the bare name; a number read backed by one vote only cannot mark `exact` (set or HP can vouch for it). Every `exact` in the sample set is now the right print. Still open: tiny / glared number lines (Lugia e-card 149/147 which prints higher than the read regions, Charizard 4/102, Salamence 3048, Charmeleon 3043), promo numbers with letters (Celebi XY93), IMG_2994 glare (374 vs 137), IMG_3033 Sneasel name, Sprigatito MEP 061 (data gap: set missing from the catalog, not chased).)* *Pass 3 (2026-11-10, same 42 photos): top-1 23 -> 23, top-3 26 -> 27 (62 % -> 64 %), in the list 38, name 41, number read 31 (25 right), no change in number reads. New weak signal `number_tail` (weight 2, label "partial number"): OCR often drops the leading digit of the collector number ("4" for 94, "7" for 187); a print whose number ENDS with the read gets the signal, `trusted` keeps the printed total for such a read, and it can never make `exact`. Gain: Salamence 3047 rank 4 -> 2 (177 and 187 tie on a one-digit read, a real ambiguity). Tried and NOT kept (no code left): warping the number region straight from the photo instead of via the 630 px sleeve flat (1x / 1.5x), other tesseract page modes and fixed / adaptive thresholds, isolating glyph blobs (connected components) before OCR. The number line is legible to a human in the crops but tesseract fails on glare streaks, the star, copyright text and card edge around it, and a bigger flat does not help. Sneasel 3033 is read upside-down / mirrored on most stages and surfaces only as fragments ("easel"); fixing it needs looser name matching, which risks false hits catalog-wide, so it was not changed. **Open (OCR limits, only a different approach helps, e.g. the image-match fallback or a digit-shape model):** no number read on Charizard 3037 / 3039, Lugia 3040 / 3042, Charmeleon 3043, Salamence 3048, Celebi 3049-3051; IMG_2994 glare; IMG_3033 Sneasel; Sprigatito MEP 061 (data gap).)* Original note: Current raw baseline (42 photos): name read 35/42, number read 14/15; misses IMG_2994 (374 vs 137), IMG_3033 sneasel, IMG_3046-3048 salamence ex, IMG_3052-3054 Ethan's Typhlosion (sleeved, sideways). Raw scans work: the right print is in the candidate list, but not always first (example: a Snorlax whose print was somewhere down the list). Wanted: rank the right print higher (more signals, better number/total reads, owned sets first), then run the whole `tests/private/scan_samples` set (raw labels.json 39 photos, labels_slabs.json 24 photos) and fix the misses one by one, reporting hit rate and top-1 / top-3 rank, not only "in the list".
5. Image-match fallback (DONE 2026-11-10: artwork signal, top-1 23 -> 31, see decisions.md 'Artwork match'), extra languages. *(Japanese cards: 2 of the 8 private slabs are Japanese (Slowking 199, Charizard V 153, no printed total); the catalog is English only, so they cannot match yet. Later, with the language decision D4.)*

**Done when:** from a cold start, scanning and adding a raw card with condition takes < 15 seconds on the phone, and ambiguous cards (Base Set Charizard) always show the version choices.

---

# Phase 3 — Turn the collection into cash

## Step 6 — Photos, listings tracker and selling `[~]` HIGH PRIORITY chain (user 2026-11-11): 6a photos -> 6c listing pack -> 6e assisted Vinted publish -> 6d reprice + sold alerts

### 6a. Photos on my cards `[x]` built 2026-11-11, awaiting the user's check (decided: Mongo `photos` collection, compressed JPEG, photos belong to the stack; decisions.md 'Photos on stacks and assisted publish')

- **Built:** phone add sheet "Save photo with the card" (default on, remembered; saves the guide crop the OCR used, <= 1000 px), "Add more photos (back, corners)" after the add, drawer `PhotosPanel` (upload, cover, reorder, delete, full size), Collection filter "Photos", Settings > Data > Photos (count, MB), `backup.sh --no-photos`. Not built: guided capture is not offered in batch mode; no cover thumbnail in the grid view / card page; no photo in export/import JSON (backup only); photos are not kept after a stack is sold or removed.
- **Saved at scan time (user 2026-11-11):** when a card is scanned (raw or slab) the phone can keep that photo with the card ("Save photo", remembered, default on), and add more right after identification (guided back / corners) or later from the card drawer. Stored compressed (long side 1600 px, JPEG), in the app's own database, so listings can reuse them.

- Attach photos to any stack/copy: front, back, corners/surface close-ups, slab front/back. A guided capture flow from the phone ("front → back → corners") so listing photos are consistent.
- Photos belong to a _specific copy_ (a PSA 9 and a raw copy of the same card have different photos).
- Mark one as the cover photo; reorder; delete; replace.
- Photos stay on the user's own machine (no cloud) and are included in backup/export.

### 6b. Mark cards for sale and track their status `[x]` built 2026-11-10 (awaiting user check; decisions.md "Sale status and realised profit")

- Each copy has a sale status: **Not for sale → Ready to list → Listed → Sold** (also: Reserved, Withdrawn).
- "Listed" records **where**: Vinted, Cardmarket, eBay, Marktplaats, other — a copy can be listed in more than one place at once.
- Per listing: asking price, listing date, link, notes, shipping cost assumed.
- **Sold:** record sale price, date, platform, fees and shipping paid → app computes **realised profit** vs. cost. Sold copies leave the active collection value but stay in history (realised P/L, sales report).
- When a copy sells on one platform, it's flagged to delist from the others.
- Views: "Ready to list", "Listed (by platform)", "Sold" with totals — € listed, € sold, realised profit, average days to sell.
- Dashboard shows listed value separately from unlisted.

### 6c. Export for listing `[x]` built 2026-11-11, awaiting the user's check (decisions.md 'Listing pack')

- **Built:** Collection selection bar > "Listing pack" drawer: platform (Vinted / Cardmarket), price strategy (match market / under by N % / floor), editable title, description and price per stack, copy buttons, photos .zip (cover first), Cardmarket CSV sheet, "Mark as Listed" (saves listings via the sale endpoint, other platforms' listings kept). Not built: Vinted category / condition / brand mapping and the real Cardmarket upload format (idProduct), both belong to the 6e research; slabs are left out of the Cardmarket sheet.

Original brief:

- Select copies → export a **listing pack**: title, description text (card, set, number, language, condition, edition, cert for slabs), suggested price, photos, in a ready-to-paste form per platform. Platform formats differ (Vinted title/limits, Cardmarket bulk-upload sheet) — start with the 2 the founder uses most.
- Suggested price from market data with a choice of strategy (match market / slightly under / floor price), always editable.
- After export, offer to mark them "Listed" with the platform and date.

### 6e. Assisted publish on Vinted `[~]` slices 1-3 built 2026-11-11 (queue + API, Publish UI in the listing pack drawer, recipe in docs); dry run on one card and real runs pending the user (HIGH PRIO; user wish: creating the listing in the app should create / update the publication)

- **Research DONE 2026-11-11:** `docs/vinted-sell-flow.md` (fields, `data-testid`s, category, condition, parcel sizes, 20 photos, mapping decided by the user).
- **Decided flow (user 2026-11-11, amends the earlier "user presses Publish"):** the app has a **Publish table** (one row per selected stack: title, description, price, Vinted condition, parcel size, photos; prefilled from the 6c pack and the mapping, all editable). The user **confirms each item in the app** (that confirmation is the approval). Confirmed items go into a `publish_queue` (Mongo). A Claude session with Chrome (the backend cannot drive the browser) works the queue **one item at a time** in the user's logged-in browser: new item -> `/items/new`; item with a stored link -> its edit page (updates price / text). It fills by `data-testid`, uploads photos from a temp folder the app writes, clicks Upload / Save, reads the item URL from the page, saves it on the stack's Vinted listing (existing `PUT /{id}/sale`, marks Listed) and reports the result to the queue. No credentials stored; the user only confirms rows.
- **Built (slices 1-3):** `publish_queue` service + `/api/publish/*`, photos written to `publish_tmp/<id>/`, Publish rows in the Listing pack drawer (condition, parcel, per-row confirm, queue list with Cancel / Release / Retry), recipe in `docs/vinted-sell-flow.md`. **Built (UX fixes, 2026-11-11):** Publish / Update on Vinted button + state in the stack drawer Sale panel, price / text prefilled from what was last published (market price only a suggestion), queue view in Settings > Data. **Pending:** dry run on one card (stops before Upload), real run one by one after the user's OK, verify Vinted title / description limits.
- Mapping: category Single trading cards (raw and graded), brand Pokemon, condition raw = Very good / slab = New without tags, parcel Small raw / Medium slab, all editable per row; decks later use "Card decks".
- Risk accepted: Claude presses Upload (account-ban / terms risk); the per-item confirmation is the only gate. First run is a dry run on one card that stops before Upload.
- Other platforms (Cardmarket sheet, eBay API, Marktplaats) follow the same pattern later.

### 6d. Price watch for listings `[ ]` (HIGH PRIO, after 6e or alongside 6c)
- **Added 2026-11-11:** daily notification / alert about (a) the market price of each listed card moving and (b) the same card **selling** elsewhere (sold comps from the existing sold-price pool), so the asking price can be corrected.

- **Decided 2026-11-10 (D3):** a **daily price sync for listed items** (reuse the scheduled refresh) feeds a **Reprice table**: card, platform, current asking price, new market price, change in % and amount, **suggested price = market + markup (default 10 %, configurable)**. The user edits the price if wanted and confirms; confirm saves the new asking price on the listing in the app and flags "update on platform". It does **not** push to the marketplace (Vinted has no seller API, Cardmarket access is restricted; nothing that risks the seller account). Per-platform push is researched later (eBay API possible).
- Alert/inbox item when a sync finds listings whose market moved beyond the threshold; "listed price is X% below/above market" indicator.

**Done when:** a card can go from scanned → photographed → exported → (published) → listed → sold with realised profit, entirely tracked in-app.

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
  - pulled cards default to acquisition = "Pulled" with an **optional cost allocation** (**decided 2026-11-10 (D8): no cost allocation**; pulled cards are excluded from P/L, which covers bought cards only, but count in collection value).
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
| D2  | **ANSWERED 2026-11-10: Vinted + Cardmarket** (Vinted title/description pack, Cardmarket bulk-upload sheet). | Step 6c | eBay and Marktplaats later. |
| D3  | **ANSWERED 2026-11-10: daily reprice table, confirm = app only.** See 6d. **Amended 2026-11-11:** Vinted gets assisted publish (6e, browser filled, user clicks Publish). | Step 6d / 6e | No API push to platforms (Vinted has no seller API, Cardmarket restricted); eBay API possible. |
| D4  | **ANSWERED 2026-11-10: Japanese Pokémon first** (TCGdex has Japanese data), other TCGs later. BUILT 2026-11-10: Settings > Catalog > Japanese sets (import on demand). | Step 5 languages/catalog | Fixes the 2 Japanese slabs (Slowking 199, Charizard V 153). |
| D5  | Switch on scheduler + backup schedule now?                               | Step 1–2                 | Backups matter more once photos and sales history exist. Backup schedule installed 2026-11-10; app scheduler still off.                                                                |
| D6  | **DONE 2026-11-10: default flipped to TCGdex** (rehearsed on a scratch copy; Cardmarket-led prices accepted). Image re-point BUILT 2026-11-10 (Settings > Catalog > Card images; run it before 2027-03-01, decisions.md "Catalog default flipped to TCGdex"). | —                        | Rollback: `CATALOG_PROVIDER=pokemontcg`. |
| D7  | Scan accuracy bar: is "pick from candidates" acceptable for every scan?  | Step 5                   | Assumed yes (never auto-add).                                                                                                                                             |
| D8  | **ANSWERED 2026-11-10:** pulled cards carry no cost and are excluded from P/L (P/L only for bought cards); all cards, pulled and bought, count in collection value. | Step 7 | No cost allocation. |

# Risks

- **Scrapers break** when a site changes layout; bulk fetch (step 1) will surface this faster and louder. Show per-source health on the dashboard. Paid/official price API remains an open option.
- **Bulk scraping gets blocked** (Cloudflare/rate limits). Keep pacing conservative; slow completion is acceptable.
- **Scan misidentifies a variant** (1st edition vs. unlimited) → wrong value. Mitigated by never auto-adding and highlighting variant markers.
- **Marketplace terms.** Unattended automation of Vinted/Cardmarket may violate terms. Decided 2026-11-11: assisted publish only (the user is in the loop and presses Publish in their own browser, no stored credentials); no unattended posting unless an official route exists.
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
| 2026-11-08 | 5 | Planned item 3b: "Scan raw cards" / "Scan slabs" buttons on the laptop, session carries `mode`, phone follows it (user: the phone always found the raw card). Built later the same day. |
| 2026-11-08 | 5 | Built item 3b: laptop "Scan raw cards" / "Scan slabs" buttons, `mode` on `scan_sessions`, phone applies it on a new session id without saving it. Tests: 3 backend, 4 vitest. Live phone check pending. |
| 2026-11-08 | 5    | Re-prioritised after the live slab test: slab scan too slow (~20 s) and shows the raw-card match first. New top item 5f: identify a slab from grader + cert number via the grader's cert page (ACE, PSA, Beckett, CGC, SGC registry), keep a report link per slab, cache the details, match the catalog from them. 5g: missing cards (Blastoise-EX 142 exists in the catalog; needs the user's repro path + a coverage audit). Slab position reader built (label 17 -> 21 of 24, grade 6 -> 15, 7.8 s). |
| 2026-11-09 | 5    | 5f slice 1 done: graders verified with real requests. ACE plain httpx; PSA / Beckett free in a browser but Cloudflare-blocked for plain HTTP, so via the host fetcher (new sites, `sites.json` hot reload, `/health` sites, no restart to add graders); CGC / SGC link-only. Matching signals per grader differ. Pending work committed (position reader, gate no-cache). |
| 2026-11-09 | 5    | 5f slice 2 done: fetcher sites are data (`psa`, `beckett` built in, `sites.json` hot reload, `/health` sites, `scripts/fetcher.sh restart`); unattended fetches wait the Cloudflare challenge grace; `providers/grading/` (ACE httpx, PSA / BGS via fetcher, CGC / SGC link-only) with real captured fixtures. Live: ACE 0.5 s, PSA 2.4 s, BGS 3.6 s. |
| 2026-11-09 | 5    | 5f slice 3 done (aeb0376): `services/slab.py` (Mongo cert cache, catalog match by name + number + total with set / year bonus, PSA / BGS never exact), `GET /api/scan/cert`, slab identify = label + cert lookup only, `report_url` + `cert_info` on the grading doc. Phone test found noisy page names (BGS appends the rarity) and an unguarded cert misread: re-planned as 3b (set-first token matching, rarity signal) and 3c (label-vs-page warnings) before the phone result card. |
| 2026-11-09 | 5    | 5f slices 3b + 3c (full pytest green; phone check pending): set-first token matching (`resolve_sets`, name words inside the resolved sets, global fallback, NOISE list instead of TRAIL), `rarity` signal (bonus), `warnings` in the cert answer (grade / tier vs label, non-Pokemon page, cert length), laptop-only `GET /api/scan/certs/recent`. Tests from the real BGS / PSA / ACE captures and synthetic noise classes. |
| 2026-11-09 | 5    | 5f slice 4 done: phone slab result card (`SlabResult`: page summary, label-vs-page warnings, edit grader / cert and look up again, then AddSheet), user phone check: works well. Two new findings: (1) Garchomp & Giratina GX #228 "not found" although `sm11-228` is in the catalog (path unknown; set-code lookup `UNM` returns nothing: probable bug); (2) prices are stored for almost every catalog card, not just collection + wishlist. New order: 5h price scope, then 5g coverage audit + set-code fix, then slab slices 5-6. |
| 2026-11-09 | 5    | 5g + 5h done (b1f7a06). Slab slice 5 measured, no code kept: the read is 6.1 s/photo, all tesseract (~29 calls); psm / width tweaks lose grades without helping certs. Slices 5 + 6 merged into one "locate the label, read only it" piece (`temp/plan_slab_5_6.md`). |
| 2026-11-09 | 5    | 5f slices 5 + 6 done (one piece): `locate_label` + read only the label crop, per-grader cert rules (`CERT_SURE`), targeted cert corner reads, grader from cert length, unsure certs never looked up (second read retried, phone card hint), tile reader only as fallback. 24 slab photos: grader 17 -> 21, cert 12 -> 20, grade 15 -> 12, calls 28.7 -> 18.1, 10.1 s -> 5.1 s (host load ~5). Not met: grade >= 15 and <= 10 calls average (fast path is 7-10; ~5 hard photos fall back). decisions.md "Slab label: locate, then read only it". |
| 2026-11-10 | 5    | Artwork match fallback (`services/artmatch.py`, `providers/ocr/imagematch.py`, `providers/catalog/images.py`, `art_cache`): raw photos top-1 23 -> 31, top-3 30 -> ~39; hint only, never exact. See decisions.md 'Artwork match for unread number lines'. |
| 2026-11-10 | 5    | "Import this Japanese set" prompt on a scan / slab with no match (`JaImportPrompt`, `services/ja_suggest.py`, `/api/scan/ja/*`, phone gate +3 routes): suggest by printed set code / English name alias / search, one confirm, progress, match runs again; catalog only. The two ja slabs read from the photos: Charizard V = S9 #103 (sample label 153 was wrong), Slowking = Neo Genesis, not in TCGdex ja. |
| 2026-11-10 | D6   | Catalog default flipped to TCGdex: weekly import skips known cards (no per-card requests), Pocket / declined sets never listed, audit fixed for bare set docs, provider tests. Rehearsal on a scratch DB: 18 of 19 tracked cards priced, 11 headline prices moved >20 % (Cardmarket-only). Images still on images.pokemontcg.io (open). |
| 2026-11-10 | D6   | Image re-point built: `services/catalog_images.py`, admin routes `catalog/images/{status,repoint,restore}`, Settings > Catalog "Card images". Reversible (`images_legacy`), idempotent, one request per set. Real run waits for the user's OK (backup first). |
| 2026-11-10 | 6b   | Sale status built: `sale` on a stack (ready / listed with listings per platform / reserved / withdrawn), sold = exit with platform, fees, shipping, realised profit, days listed and delist hint; filters, presets, bulk status, Dashboard listed value, Settings > Data > Sales. Whole-stack granularity. |
| 2026-11-11 | 6a   | Photos built: `photos` collection (Pillow-compressed JPEG + thumb), API + phone `POST /api/scan/photo` (only for a just-scanned stack), save toggle + extra shots on the phone, `PhotosPanel` in the drawer, `has_photos` filter, Settings > Data > Photos, `backup.sh --no-photos`. Tests: test_photos.py, Scan.photo / PhotosPanel vitest. |
| 2026-11-11 | 6c   | Listing pack built: `services/listing_pack.py`, `POST /api/collection/listing-pack`, `listing-pack.csv`, `photos.zip`, `ListingPackDrawer` on the Collection selection bar. Tests: test_listing_pack.py (8), ListingPackDrawer vitest (2). |
| 2026-11-11 | 6e   | Vinted sell flow researched read-only in Chrome (`docs/vinted-sell-flow.md`); mapping and flow decided with the user: Publish table with per-item confirm in the app, `publish_queue`, Claude works it one by one (create or update via stored link), reads the item URL back. Build not started. |
| 2026-11-11 | 6    | Re-prioritised after the user's request: photos saved at scan + added later (6a, building), listing pack (6c), assisted Vinted publish (new 6e), daily reprice + sold-comps alerts (6d) all high priority, in that order. D3 amended. |
