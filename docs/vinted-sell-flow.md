# Vinted sell flow (researched 2026-11-11, vinted.nl, English UI, logged-in account)

Read-only walk of `https://www.vinted.nl/items/new` (nothing uploaded, nothing published). Used by roadmap Step 6e (assisted publish: Claude in Chrome fills the form, the user presses Publish; no credentials stored).

## Form fields (order on the page)

| Section | Field | Kind | Notes |
| --- | --- | --- | --- |
| Photos | Upload photos | button / file input | Up to **20 photos** per listing (Vinted Help Centre summary). Not tested live; first photo = cover. |
| About your item | Title | textbox "Tell buyers what you're selling" | 6c limit constant 100 not verified on the form. |
| About your item | Description | textbox "Tell buyers more about it" | 6c limit constant 2000 not verified on the form. |
| Item details | Category | searchable picker | Search "trading card": **Hobbies & collectables > Trading cards > Single trading cards** (others: Trading card lots, Card decks, Uncut card sheets). |
| Item details | Brand | searchable picker | Appears after the category. "Popular brands" list has **Pokémon**, Topps, Panini, Yu-Gi-Oh!. |
| Item details | Condition | picker | Appears after the category. Options: **New with tags, New without tags, Very good, Good, Satisfactory**. |
| Pricing | Price | textbox, placeholder "€0.00" | EUR. |
| Shipping | Parcel size | radio cards | **Small** (large-envelope size, "Recommended" for cards), Medium (shoebox), Large (moving box). Buyer always pays postage. |
| Footer | Save draft / Upload | buttons | "Upload" = publish. The assisted flow must stop before it. |

Dependent fields (Brand, Condition, Shipping) only exist after a category is chosen. Leaving the page with edits triggers a browser "Leave site?" dialog: the fill step must not navigate away mid-fill.

## Decided mapping (user, 2026-11-11)

- Category: **Single trading cards** for raw and graded (decks later use "Card decks").
- Brand: **Pokémon** (other TCGs later).
- Condition: raw -> **Very good**; graded (slab) -> **New without tags**. Editable per item in the confirm table.
- Parcel size: raw -> **Small**, slab -> **Medium**; editable per item.
- Title: card name, number, set, condition or grader + grade (user thinks the limit is ~200; verify on the form, the 6c constant is 100 until then).
- Description: short, natural card description (name, number, set, condition) plus a common service line ("shipping fast and with care").
- Price: EUR, from the per-item confirmation table (suggested price, user can edit).
- Publish: user confirms per item **in our app**; Claude then fills and uploads in the logged-in browser (user decision, amends the earlier "user presses Publish"). Update: the stored Vinted link opens that item's edit page. The item link is read from the Vinted page after publishing and saved on the stack's Vinted listing.

## Form hooks (from the pasted DOM)

Stable `data-testid`s: `add-photos-input` (hidden `input[type=file]`, accepts jpeg/gif/png/webp, multiple), `title--input`, `description--input`, `catalog-select-dropdown-input` (category), `brand-select-dropdown-input`, `category-condition-single-list-input`, `price-input--input`, `1|2|3-package-size--cell` (Small/Medium/Large), `upload-form-save-draft-button`, `upload-form-save-button` (Upload).

## Not verified / fragile

- Photo limit 20 comes from the Help Centre, not from the uploader.
- Title / description character limits (check by typing past the limit).
- Vinted may change labels or pickers; the fill recipe should address fields by visible label, not position.
- Other Vinted domains (.fr, .de) have other UI languages.

## Fill / upload recipe (Claude session with Chrome; slice 3, dry run first)

Queue API (backend, `http://localhost:8100`, no auth): `POST /api/publish/queue/next` claims the oldest confirmed item (state `publishing`, returns `payload`, `mode`, `open_url`, `files` = photo paths relative to the repo root, cover first) or `null`. Report with `POST /api/publish/queue/{id}/result` `{"state":"published","url":...}` or `{"state":"failed","error":...}`; `POST .../release` gives the item back untouched (use it when stopping). A published result saves the stack's Vinted listing (Listed + link) itself; no separate `PUT /sale` is needed. One item at a time: `next` refuses (409) while one is still `publishing`.

Per item, in the user's logged-in Chrome, one tab:

1. Claim: `next`. Empty = stop. Use `payload` exactly as confirmed; never edit text or price.
2. Open `open_url` (`/items/new`, or the edit page when `mode` is `update`; the edit-page path `/items/{id}/edit` is derived from the stored link and is unverified: if it 404s, release the item and tell the user).
3. Stop and tell the user on any login prompt, CAPTCHA, verification or unexpected dialog. Never solve or dismiss them blindly. Release the item.
4. Photos (create only; on update leave existing photos unless the user asks): the file tool must be given absolute paths (`<repo root>/` + `files[i]`), set on `[data-testid=add-photos-input]` in one call, cover first, max 20. Wait until all thumbnails show.
5. Fill by `data-testid` (re-check on the page; fall back to the visible label if one changed): `title--input`, `description--input` (type, do not paste via script), then category: `catalog-select-dropdown-input` -> search "trading card" -> Hobbies & collectables > Trading cards > Single trading cards; then brand `brand-select-dropdown-input` -> Pokémon; condition `category-condition-single-list-input` -> `payload.condition`; `price-input--input` -> price in euros with a comma or dot (`1500` cents = `15.00`); parcel `1|2|3-package-size--cell` = small|medium|large per `payload.parcel`.
6. Read every field back from the page and compare with the payload. Any mismatch: fix, or fail the item.
7. **Dry run**: stop here and show the user (screenshot). Do not click Upload / Save. Release the item (`release`) so it stays confirmed.
8. **Real run** (only after the user's OK for the first Upload): click `upload-form-save-button` (update: the save button of the edit form), wait for the redirect to the item page, read the item URL from the page address, report `published` with that url. If the click leads anywhere unexpected (error banner, bot check), report `failed` with the text and stop.
9. Do not navigate away mid-fill (Vinted raises a "Leave site?" dialog). Next item only after the previous one is reported.

Limits to verify on the form during the dry run (type past the limit, read the counter / error): title (user thinks ~200; app payload accepts up to 200, listing pack still cuts at 100), description (pack cuts at 2000).

## Verified in the first real runs (2026-11-11, 3 cards published)

- The file tool accepts the absolute `publish_tmp/<id>/NN.jpg` paths; `add-photos-input` takes both photos in one call, first = Main.
- Vinted fills **category (Single trading cards) and brand (Pokémon) itself** from the title; only check them. Condition and price stay to do. Category path on the item page: Hobbies & collectables > Trading cards > Single trading cards.
- Choosing **New without tags** opens a dialog "Item must be unused" offering "Very good": raw cards use Very good (the app default), so no dialog. Never click through it blindly.
- Click the fields by `find` ref, not by pixel coordinates (the layout shifts after the photos upload; one description typed into nothing). Typing works with emojis and newlines; read every field back by `data-testid` after typing. Vinted formats the price to "€7.00" on blur.
- **After Upload Vinted redirects to the member profile (`/member/<id>?promo_shown=true`) with an "Item listed" popup, not to the item page.** Find the new item there: the newest link `a[href*="/items/"]` whose title starts with the card title; open it and take the canonical URL (`/items/<id>-<slug>`). That is the url reported to the queue.
- **Title and description limits are not verifiable on the form**: no `maxlength`, no counter, no error on input or blur up to 300 / 5000 characters. They only show on submit. Payload caps stay 200 / 5000; the pack cuts at 100 / 2000.
- **Edit page verified 2026-11-11 (first real update, Spiritomb 4.00 -> 4.50):** `/items/{id}/edit` opens the filled form (photos, title, description, price `price-input--input`, Save button). Change only the price, read back, click Save: Vinted redirects to the member profile (item shows "Processing"), the item URL stays `/items/<id>-<slug>` unchanged; report that same url. Triple-click on the price field by pixel worked after the layout settled; a first attempt failed with "Cannot access a chrome-extension:// URL of different extension" (another extension's popup had focus); a fresh tab group fixed it.

## Chrome extension (primary, built 2026-11-12)

`extension/` runs the same recipe inside the user's own logged-in Vinted tab (see `extension/README.md`, decisions.md). `recipe.js` is the port of `recipe.py`: same data-testids, guards (login URL, CAPTCHA text, 404, open dialog, missing auto-fill, read-back mismatch) and update mode (title / description / price only). Photos come from the app as blobs and are set on `add-photos-input` via DataTransfer. Dry run = popup toggle (default on). Not yet proven live: condition picker, parcel cell, slab dialog.

## Host publisher script (secondary, built 2026-11-12, no Claude)

`scripts/publish.sh [--dry-run] [--max N]` runs this recipe with Playwright in the fetcher Chrome profile (`fetcher/fetcher/publisher/`: `recipe.py` steps, `runner.py` queue loop, CLI `python -m fetcher.publisher`). On demand only, default 1 item per run, daily cap `FETCHER_PUBLISH_MAX_PER_DAY` (10), random pauses, `FETCHER_PUBLISH_MIN_GAP_S` between items. First time: `scripts/publish.sh --login` opens https://www.vinted.nl/ in that profile; log in by hand (never stored by the script). Update mode fills title, description and price only (verified flow); create mode also photos, condition and parcel, and only checks that category / brand were auto-filled. Any login, CAPTCHA text, open dialog (incl. 'Item must be unused'), 404, missing auto-fill or read-back mismatch releases the item and stops the run (screenshot in `~/.moc-fetcher/failures`). After Upload, a missing redirect or missing item on the profile marks the item `failed` (not re-queued, check Vinted). **Not yet proven live:** condition picker option click, parcel cell click, slab condition (dialog -> released). The old Claude recipe above stays the fallback.
