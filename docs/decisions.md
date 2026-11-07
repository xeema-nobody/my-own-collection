# Decisions (discovery, Phase A)

Answered by user: Q6/Q7 EUR base, EN+JA; Q12 full catalog in background (dev: base1 + sv3pt5); Q20 commit per phase on a feature branch, local only, no push.
Local-only run: docker compose, mongo with named volume `moc_mongo_data` (survives `down`; never use `down -v`).

Asked by user, answered:
- Q1 PriceCharting: **superseded** (see Scraping decisions). No API token, no paid plan. Data via browser fetcher.
- Q2 alt.xyz: **superseded**. Fetched by the browser fetcher (sold list works anonymously); manual sale entry (`POST /api/cards/{id}/sales`) stays as source `manual`.
- Q4: aggregate = provider-computed market number; sold = individual completed sales. Both stored with `kind`; sold stats (last 10 / 90d) shown when sales exist, aggregate badged otherwise. User wants statistics from trustworthy data -> prefer sold when available.

## Scraping decisions (user, 2026-10-27)
1. Sold-price scraping: YES. Sources PriceCharting, Cardmarket, alt.xyz (+ pokemontcg.io aggregate as optional 4th). Shown in card detail, collection, dashboard.
2. No PriceCharting token. Catalog stays pokemontcg.io (no Scrydex).
3. Sold = real value (D-A). Roadmap: graded pricing -> scheduler -> alerts.
4. Fetch only when the user asks (card button; Settings: set / owned / one card). Each site is tried without login first; if login or a challenge is needed a visible tab opens on that site, the fetch waits ("waiting for login (<site>)"), the user logs in themselves, fetch continues. We never see or store credentials. Sessions persist in a dedicated Chrome profile.
5. Fetcher runs on the host Mac (not Docker); the app calls it over localhost HTTP. Browser closes after idle.

Defaulted by me (change on objection):
- **D-A** value per copy = sold-based price if >=3 sold sales in last 90d for that card+grade (median of last 10); else source market/trend aggregate; else unpriced. Each price has `kind` (`sold|market|ask`), UI badges it, never mixed silently. Median, not mean. `manual` highest trust.
- **D-B** one host-Mac fetcher driving **real Google Chrome over CDP** (`--remote-debugging-port`, dedicated `--user-data-dir`), Playwright `connect_over_cdp`. Playwright's bundled Chromium (headless or headed) is blocked by Cloudflare on Cardmarket; real Chrome passes. PriceCharting and alt.xyz also work headless, but one engine is simpler.
- **D-C** on demand only, polite: 1 request / 3-5 s per site, concurrency 1 per site, cache 24h, no bulk catalog crawl.
- **D-D** one observation per (card, variant, source, kind, grade_key, fetch date); upstream `as_of` kept as field.
- **D-E** store native currency, convert to base at read via FX.

Defaults taken (assumptions): Q3 cardmarket aggregates from catalog payload; Q5 keyless pokemontcg.io (works, flaky: retries on 5xx); Q8 graders PSA/BGS/CGC/SGC/ACE/OTHER; Q9 stacks (slabs w/ cert unique); Q10 P/L on; Q11 from scratch; Q13 collection daily + catalog on demand; Q14 scheduler off; Q15 local, no auth, bind 127.0.0.1; Q16 Vite SPA, dark+light, English; Q17 api 8100, web 5180, prefix `moc-`; Q18 Pokemon only; Q19 backup service deferred to Phase 7.

## Data source findings (2026-10-27)
- pokemontcg.io is **deprecated**: new keys closed, existing keys valid until 2027-03-01; keyless works but returns intermittent 500/502 (retried with backoff).
- Successor Scrydex: paid, from $29/mo (5k credits), includes raw+graded prices. Not adopted; swap in via `CatalogProvider`.
- Frankfurter moved to `api.frankfurter.dev/v1`.
- Cardmarket `updatedAt` in the payload can be months old: shown as `as_of`.
- Product matches live in their own collection `product_matches`, not `cards.external_ids`: catalog import rewrites `external_ids.cardmarket_url` (aggregate link) on every run. User-confirmed matches take precedence over auto ones.

## Phase 4: graded valuation (2026-10-28, defaults by me, change on objection)
- Ask prices are never used for valuation.
- A company-agnostic bucket match (`G9` for a PSA 9) is NOT exact: shown with `≈` and a reason.
- Sold rule (>=3 in 90 d, median of last 10), `PREFERRED_SOURCES` order are settings in `app/config.py`; no Settings UI. Sold sales are pooled across sources.
- Scraped raw sales never value raw items (condition unknown); manual ones do.

## Phase 5: dashboard (2026-10-28, defaults by me, change on objection)
- `PREFERRED_SOURCES` = `pricecharting,tcgplayer,cardmarket_web,cardmarket,altxyz`: cardmarket_web gave ~2-3x the other raw prices for Mew ex 205 (confirmed match V5); stale catalog cardmarket (as_of Nov 2025) last. Revisit after the product version is verified.
- Market points older than 180 days lose to any fresher source (setting `MARKET_MAX_AGE_DAYS`).
- Movers = same valuation now vs N days ago; only comparable (same kind / grade match) items.
- Demo data lives in a separate database `owncollection_demo` (user choice), not tagged items in the real one.
- Cards with several prints/versions sharing a number (Cardmarket V3/V4/V5, `[Metal]`) have different prices: the UI shows the matched product slug and warns when picking among candidates.

## Phase 5b: compare sources (2026-10-28, defaults by me, change on objection)
- The Cardmarket "confirmed V5" for Mew ex 151 #205 was wrong: V5 is the **oversized** (jumbo, "Not Tournament Legal", 2 listings, trend 49.66), V4 is the Metal Card (Ultra-Premium Collection), V3 is the standard Hyper Rare (trend 24.15, in line with PriceCharting / tcgplayer). Match switched to V3 and re-fetched. `PREFERRED_SOURCES` order left as is.
- Every source's value is shown next to the headline with kind, match, thin, data age and matched print. The headline rule is unchanged, only explained (`headline_rule`).
- Outlier flag: a source is flagged when it is more than `OUTLIER_PCT` (40) % from the median of the sources that priced the item the same way as the headline (same match type; a raw fallback next to a graded price is not compared) and at least 3 sources have a value. With 2 sources only the gap is shown.
- Matched print comes from the stored product url (slug, Cardmarket `V<n>`), titles are kept when the user picked among candidates. The matcher still cannot tell V3/V4/V5 apart on its own: it needs a user pick (`needs_match`).

## Phase 7: alerts (2026-10-28, defaults by me, change on objection)
- Evaluated at the end of `take_snapshot` (covers manual and scheduled fetch, refresh, snapshot). One event per crossing, re-armed when the condition clears; unknown values never change state.
- Estimated / fallback values do not alert unless the rule opts in. Thin sold values alert, flagged.
- Stack scope is the default target (the stack is what is valued); card scope sums all stacks of a card.
- No macOS notification: the API runs in Docker. Idea: the host fetcher polls `/api/alerts/events?unread=true`.
- Fix found while testing Phase 6 live: single-hit search redirects (PriceCharting, Cardmarket) and alt.xyz rarity filter caused `not_found` (see pricing.md).

## Phase 6: scheduler (2026-10-28, defaults by me, change on objection)
- Scheduler stays opt-in (`SCHEDULER_ENABLED=false`). Four independent tasks: catalog-API refresh of owned cards (04:00), scraped fetch of owned cards (04:30), snapshot (06:00), full catalog import (Sun 03:00). Times are container time (UTC).
- Scheduled fetches are **unattended**: the fetcher fails a login/challenge page at once (`login_timeout` / `blocked`, "unattended: ...") instead of opening Chrome and waiting; the run then skips that site. Log in manually (Settings fetch) to restore the session; the next scheduled run uses it. If the fetcher is not running the run is recorded as a `skipped` job. No notification yet.
- Cap 300 cards per scheduled fetch, stalest first (by last attempt in `fetch_log`, never-tried first). No resume state: fetched cards become fresh, so the next run takes the rest.
- Boot catch-up: each task whose last `ok|partial` run is older than 24 h (7 d for the catalog; snapshot by `taken_at`) runs once, in order, in the background. Catalog catch-up is skipped until a first import exists. Catch-up uses the same cache-skip, so a manual fetch earlier the same day is not repeated.
- `jobs.trigger`: `manual` (default for API calls), `scheduler`, `catchup`. Older rows lack it (UI shows manual).

## Phase 8: export / import (2026-10-28, defaults by me, change on objection)
- JSON (`{"format":"moc-collection","version":1,"items":[...]}`) is the lossless format; CSV is flat for spreadsheets (money in integer cents, tags `;`-joined, `name/set/number` columns are read-only context). Import of an unknown `version` is refused.
- Import upserts on `stack_key`. Default mode `set` overwrites quantity and the editable fields (acquired, notes, tags), so re-importing a file is a no-op and an export doubles as a restore; mode `add` increments quantity instead. Rows that fail validation or reference an unknown card are reported by row number and skipped; the rest are applied (no all-or-nothing).
- Upload is the raw request body (no `python-multipart` dependency); 5 MB and 20k-row caps.

## Phase 8: backup (2026-10-28, defaults by me, change on objection)
- Host scripts, not app code: the app container cannot reach docker. `mongodump --archive --gzip` run inside the mongo container with its own env credentials, streamed to `backups/` on the host (written as `.part`, renamed when non-empty).
- Full dump by default (catalog is re-importable but slow to rebuild); `--no-catalog` for a small user-data dump. Keep newest 14 (`MOC_BACKUP_KEEP`), pruning only `moc-*.archive.gz`.
- Restore replaces archive collections (`--drop`) after a typed confirmation; `--to-scratch` verifies an archive without touching live data. Scheduling is documented (cron/launchd), not automated.

## Phase 8: perf (2026-10-28, defaults by me, change on objection)
- Measured before changing: every search/sort path < 250 ms at 20k cards and valuation < 1 s at 2000 stacks, so no new indexes and no valuation cache. Thresholds to revisit are in `architecture.md`.
- Dropped the unused `cards_text` text index (15 MB, extra write cost on catalog import). Search stays regex over `search_text`.

## Phase 8: FE error states + tests (2026-10-28, defaults by me, change on objection)
- Failed queries keep the page layout and show one red box per failed query with its own Retry (not one page-level error), so a single failing endpoint does not hide the rest. Stale data stays visible if a refetch fails after a success.
- No global toast/notification layer and no per-page loading skeletons: plain "Loading..." text where a list was blank before.
- FE tests mock `fetch` (no network, no MSW dependency) and cover the API client, `QueryState`, `ErrorBoundary`, page empty/error states, the Settings import summary and the 404 route. No browser/e2e framework; visual checks stay manual.
- Backend gap tests (fx, price matrix, unique-index constraints, same-day snapshot re-run) assert current behaviour; no app code changed. FX with no stored rate and a provider outage returns `None` (callers treat as unpriced), by design.

## Phase 8: code + security review (2026-10-28, defaults by me, change on objection)
- **Browser-origin guard** (`app/main.py`): CORS only stops a foreign page *reading* replies; a cross-site simple request (e.g. `text/plain` POST to the raw-body import, or body-less admin POSTs) still executes. Non-GET/HEAD/OPTIONS requests carrying an `Origin` not in `CORS_ORIGINS` get 403; requests without `Origin` (curl, scripts, tests) pass. `TrustedHostMiddleware` (`ALLOWED_HOSTS`, default `localhost,127.0.0.1`) blocks DNS rebinding. Test clients use `http://localhost`.
- Import body is read as a stream with the 5 MB cap enforced while reading (and `Content-Length` pre-checked), not after buffering. Bad field types in an import row (list `card_id`, non-string `created_at`) are per-row errors instead of a 500.
- `SaleIn.url` must be http(s); FE `safeUrl()` guards every `href` built from scraped/upstream data (blocks `javascript:`). `/api/admin/jobs?limit=` bounded 1-200.
- Checked, no change: search/filters use `re.escape` and typed params (no operator injection); product-match URLs validated to https + site host + path marker, and the fetcher independently enforces its per-site host allowlist; fetcher and Chrome CDP bind 127.0.0.1; mongo has no host port; `.env` is gitignored and absent from git; compose ports are `127.0.0.1`-only.
- Accepted, local-only: containers run as root; no rate limit on the API; CSV export does not escape leading `= + - @` in user notes (spreadsheet formula injection, only your own data); fetcher `/fetch` has no Origin guard (it only reaches whitelisted shop hosts).
- **RESOLVED 2026-11-02 by the toolchain bump (npm audit 0). History: npm audit (8 findings, all fixes are semver-major):** `vitest`/`@vitest/mocker`/`tinypool` (incl. the 2 critical "prototype pollution -> RCE" in tinypool worker options) and `vite`/`esbuild` (dev server readable by any website) are **dev-only**: never in the built bundle, the dev server is published on 127.0.0.1 only, and the exploit paths need attacker-controlled test config or a visit to the dev server while it runs. `react-router`/`react-router-dom` is shipped, but the advisories are an open redirect via backslash in user-supplied `<Link>`/`navigate` targets (the app has none: all targets are literals or ids) and SSR hydration (`deserializeErrors`, no SSR here). Fix needs vitest 4 / vite 8 / router 7, each a breaking migration of tooling that works; deferred until the next planned toolchain bump. Re-run `npm audit` then.
- Web container has a healthcheck (wget on :5180, 120 s start period for the first `npm install`). No prod nginx image: nothing is deployed.

## Phase 8: leftovers (2026-10-28, defaults by me, change on objection)
- **Alert prune**: only READ `alert_events` older than `ALERT_EVENTS_KEEP_DAYS` (90, 0 = off) are deleted, by a scheduler task `daily_prune` (06:30, `ALERT_PRUNE_CRON`). Not run inside `evaluate` (price-update path stays free of housekeeping) and not caught up at boot. Rule state (`triggered`) lives on the rule, so deleting events never re-fires anything. Market data (`prices`, `sales`, snapshots) is untouched.
- **alt.xyz paging**: `?page=N` is ignored by the site (client-side pagination), so the fetcher got `click_labels`. Adapter reads <= `ALTXYZ_MAX_PAGES` (3) pages and stops when the oldest sale on a page is older than `ALTXYZ_MAX_AGE_DAYS` (180); older sales are dropped. User guidance: only the last ~3-6 months of sold listings count, older ones skew low. Valuation window stays 90 d. PriceCharting / Cardmarket adapters unchanged (they read no per-sale list beyond what the page shows; their `sold_points` already use the 90 d window).
- Cost (superseded 2026-11-02): per-page navigations made alt.xyz ~1 min per card. **One-navigation paging**: fetcher request takes `pages` + `next_label`, loads once, clicks next in the same tab, waits for the tile list (hrefs of `wait_selector`) to change, returns `htmls` (one snapshot per page; `html` = first, for old clients). Stops quietly when the control is missing or the list stops changing. Adapter makes one call and keeps the dedupe / 180 d stop rules. `click_labels` kept for compatibility. Live: 3 pages in 19 s (was ~66 s). `ALTXYZ_MAX_PAGES` stays 3, no per-trigger cap.
- **"N new" label** (Alerts > Rules) is `min(fired by last Check now, unread count)` from the shared `["alerts","unread"]` query, so Mark read in the Inbox clears it.

## Phase 9.1: catalog completeness (2026-10-29)
- pokemontcg.io 500s on some pages at `pageSize=100` (sm11 page 2). `iter_cards` now uses `orderBy=number` and re-fetches a failed page as aligned smaller pages (50, 25, 5; 2 attempts each, so a dead window is cheap). Cards still unreachable are skipped and reported (`IncompletePage`), the rest of the set is kept. No number-range query: smaller pages recovered sm11 live.
- Completeness = imported cards vs the set's upstream `total` (fallback `printed_total`; unknown = complete). Stored on the set doc after every set import (`imported_count`, `complete`); the sets API computes `cards_expected` / `cards_missing` live so old imports show up too. Upstream `total` can be one lower than the real card count (sm11: 260 vs 261 imported), so `>=` counts as complete.
- A silently short set is treated as failed: job status `partial`, `stats.incomplete_sets`, warning log. "Retry failed" is replaced by "Retry incomplete" (`POST /api/admin/catalog/import/retry-incomplete`) = short sets + failures of the latest full import/retry. The weekly full import revisits every set anyway.

## Phase 9.2: valuation correctness + auto-fetch (2026-10-29)
- A graded stack with no graded price is NOT valued (a slab is not worth its raw copy): `value=None`, match `needs_graded_price`, `needs_price`, raw price kept as info (`ref_raw_value`). Bucket / lower-grade estimates stay counted, flagged `estimated` (user decision; revisit if wanted excluded too). Live effect: value EUR 955.86 -> 407.46, 10 stacks need a price (EUR 548.40 of raw copies were counted before).
- Old snapshots (no `valuation_version`) are hidden from the history chart, not rewritten or recomputed (user decision). History restarts from the first v2 snapshot.
- Movers/alerts needed no change: both already ignore unpriced items; tests pin it.
- Auto-fetch on add is best effort and lives in the FE (`lib/autoFetch.ts`): 503 -> inline "fetcher offline", 409 -> in-memory queue retried every 10 s, never blocks or fails the add. Import does not auto-fetch (banner + "Fetch missing prices" instead). `POST /api/admin/prices/fetch {"missing": true}` targets owned cards that have a needs-price stack; the 24 h fetch cache still applies.

## Phase 9.3: design foundation (2026-10-29)
- Palette: neutral dark + one emerald accent, as CSS variables (space-separated RGB so Tailwind alpha works) in `web/src/index.css`; Tailwind colours (`bg`, `surface`, `surface-2`, `line`, `fg`, `muted`, `accent`, `ok`, `warn`, `danger`) map to them. User approved the look after a preview of Search + Card page.
- Theme: class strategy (`darkMode: "class"`). **Default is dark** (user decision: not the OS setting). Toggle in the header: light / system / dark, always stored in `localStorage` (`moc-theme`); "system" is an explicit choice. A tiny inline script in `index.html` applies the class before first paint (no flash).
- Font: Inter Variable via `@fontsource-variable/inter` (local, works offline). Numbers use `.num` (tabular-nums).
- Dependencies (user OK): `lucide-react`, `@fontsource-variable/inter`, `@radix-ui/react-{select,tabs,dialog,popover,collapsible}`. Rule: wrap every third-party primitive in our own component under `web/src/components/ui/` and use only those in pages, so the look and behaviour live in one place and are reused (user: abstract reusable components). `dialog`/`popover` are installed for the Collection drawer and Combobox, not used yet.
- Legacy classes `.btn`, `.btn-ghost`, `.input`, `.card` were kept (on the tokens) until the last page was migrated; removed in the Phase 9 wrap-up.
- Restyle order (user): Collection, Dashboard, Alerts (done: guided sentence form, `Combobox` picker over `/api/collection?q=&page=` so no 200 cap, no backend change; `?stack=` label resolved from one list call; Inbox badge says "unread" so it does not clash with the Rules "N new" label; jsdom polyfills for Radix Select in `test/setup.ts`), Settings (done: five tabs with the selected-set state lifted to `Settings` so Catalog actions and the Prices scope share it; series grouping uses the `series` field already on set docs, no backend change; job summaries are derived client-side in `lib/jobs.ts`; `Chip` and `FileDrop` added to the ui kit), then PriceMatrix and the price chart (done: grade state in `?grade=` via `usePriceGrade`, `lib/grades.ts` parses matrix keys, source colours are `--src-*` tokens used as `rgb(var(--src-x))` in SVG too, no headline-cell highlight (backend does not expose the headline cell per grade), selected row highlighted instead). Search + Card page shell are done.
- Collection restyle (2026-10-29): `GET /api/collection` gains `order=asc|desc` and sorts `cost|pl|qty|set` (plus `added|value|name`); rows with no value for the sort key (None) always go last in either direction; each row has `pl` (value - cost, None if either missing). Collection UI state (filters, sort, page, size) lives in the URL. Value chart reuses `/api/dashboard/history` (legacy snapshots hidden). New shared kit parts: `Table/SortTh`, `Pagination`, `Drawer` (Radix Dialog; first use of `dialog`). Page size is not capped by the old 50 anymore: user picks 25-200.
- Dashboard restyle (2026-10-29): purpose split. **Collection = inventory** (find / edit stacks, fix missing prices), **Dashboard = insight** (how it is doing, what changed). Dashboard = KPI strip (value, 30d change, P/L, cost), `ValueChart full` (adds 7d range + compare-sources toggle), `BarList` composition (top 10 + Other, CSS bars so long set names are not cut), top holdings (`/api/collection?sort=value&order=desc&page_size=8`, no new endpoint), movers up/down, data-quality card (sold-based %, estimated / needs price / no data, Fetch missing prices via the shared `usePriceFetchJob`), source comparison collapsed. Reliability and unpriced counts moved off the KPI row. No backend change.

## Wishlist (2026-10-31, defaults by me, change on objection)
- Entry = card + variant + wanted grade (raw, or company+grade; no cert, no condition) + optional target price + note; unique on that key, adding again updates it.
- Priced exactly like one owned copy (`resolve_item` on a virtual item). A graded want without a graded price is `needs_price`, not valued, never alerts (same rule as owned slabs).
- Alert engine reused: new scope `wish` (`wish_id`), same ops and state machine and inbox. Wishlist rows are valued separately and fed only to `wish` rules, so total/stack/card rules and snapshots never include wishes.
- A target price keeps one `auto` "below target" rule in sync (`wishlist.sync_alert`): created with the target, threshold follows edits (re-armed), removed when the target or the alert flag is cleared, deleted with the entry. Extra rules via the Alerts form.
- Wishlist cards are in the scheduled fetch (`stalest_owned` = owned + wished) and `POST /admin/prices/fetch {"wishlist": true}`.
- No automatic move to the collection when a wished card is bought (no hidden coupling); no export/import (mongo backup covers it).

## Phase 9 wrap-up (2026-10-31)
- Phase 9 complete. Last legacy-class users (`QueryState` Retry, `ErrorBoundary`, `NotFound`) moved to `Button`/`Card`; `.btn`, `.btn-ghost`, `.input`, `.card` deleted from `index.css`.
- Screenshots: the Chrome tool's window resize does not change the page viewport (`innerWidth` stayed 1800), so they were taken with headless Chrome over CDP with an exact viewport override (width asserted, theme asserted via the `dark` class). 6 pages x 3 widths (1280, 1600, 2000) x 2 themes = 36 PNGs (~20 MB). Only the 1600 px set (12 files, 7.5 MB) is committed in `docs/screenshots/`; the full set stays in gitignored `temp/screenshots/` to keep repo weight down (user was unsure; this is the compromise). Card page capture is capped at 2600 px tall.

## Catalog provider: TCGdex (2026-11-03, user: trunk-based, straight on `main`)
- pokemontcg.io keys end 2027-03-01. Chosen replacement: **TCGdex** (free, no key), selectable with `CATALOG_PROVIDER=tcgdex`; **default stays `pokemontcg`** until the user flips it (backup first: `scripts/backup.sh`). Scrydex (paid) stays the fallback.
- Spike (read-only, 2026-11-03): only 14,509 of 20,670 card ids were identical. 50 of 176 sets have other ids (`sv3pt5` = `sv03.5`, `zsv10pt5` = `sv10.5b`), numbers are zero-padded (`swsh9-001`), `cel25c-17_A` is `cel25cc-CC015`, and 5 of 14 owned/wished cards had no same-id counterpart. Collection, wishlist, matches and sales are keyed on our ids, so ids are never changed.
- **Mapping**: sets by identical id, else normalised name (card total breaks ties; ambiguous = no guess), 48 of the 50 resolve (`fut20`, `me55c` have no TCGdex set). Cards by number inside the matched set (`001` -> `1`). A set whose numbers do not line up (cel25c) is left alone, otherwise it would be duplicated. Unknown numbers become new cards only in sets we never imported, or while we hold fewer cards than upstream and the numbers line up.
- **Known cards are never rewritten** (`_prices_only`): TCGdex rarity/type wording differs, so only their Cardmarket price is refreshed. Known sets are returned as bare `{_id, external_id}` so the set upsert changes nothing.
- **Price loss accepted (user)**: TCGdex has no TCGplayer prices (0 of 97 sampled cards). `_sources=("cardmarket",)` keeps a stored TCGplayer price from being unset, but it stops updating and falls out after `MARKET_MAX_AGE_DAYS`. Valuation then rests on PriceCharting, scraped Cardmarket, alt.xyz sold sales and the TCGdex Cardmarket aggregate.
- Cost: one request per card (a full import is ~20k requests, `refresh_prices` scope `collection` passes `only=` so it fetches just the owned cards). Live check on a scratch database copy: 277 cards of `sv3pt5` + `swsh12pt5gg` in ~12 s, card docs untouched, `cel25c` untouched.

- **Star cards + card page polish (2026-11-02)**: `pokemon:cel25c-17_A` (`Umbreon ★`) failed on alt.xyz because the raw `★` and a doubled rarity in the query returned no sold tiles. Fix = normalise `★` -> `Gold Star` in queries and matching, language check on alt tiles, empty search = `not_found`. PriceCharting got the same query normalisation; verified live 2026-11-03 and fixed (it files this print as plain `Umbreon #17` under `Pokemon Celebrations`, see `pricing.md`). Card page: compare table merged into one (group row per copy), Sold stats sorted and sales capped at 10 with period + title filters, Sources shows alt.xyz's search and kept listings (alt has no stored product match).

## Alert notifications on macOS (2026-11-05)
- Lives in the host fetcher (`fetcher/fetcher/notify.py`), not in the app: the app runs in docker and cannot show a macOS notification, and the fetcher is already a long-lived host process. The backend is unchanged; the fetcher only polls `GET /api/alerts/events?unread=true` every 60 s.
- Dedupe by a high-water mark (`fired_at`) + notified ids in `~/.moc-fetcher/notified.json`, not by the event's `read` flag (that is UI state). State is written only after the notification was shown, so a failure retries on the next tick.
- First run seeds silently (user decision): the existing unread backlog is not announced. Afterwards one new event shows its text, several show "N new price alerts".
- `osascript` has no click-through; it needs notification permission for the host app that runs it. Off switch `FETCHER_NOTIFY_ENABLED=false`.
- Known quirk found the same day: `scripts/fetcher.sh stop` can leave the fetcher running (pidfile holds the wrapper pid). Not fixed; see `roadmap.md`.

## Wishlist bulk refresh (2026-11-05, roadmap Step 2)
- One component, one scope: `BulkFetch` gets a Collection / Wishlist / Both picker (Wishlist page defaults to Wishlist) and `POST /admin/prices/fetch` a `scope` field; no second job type, so the one-at-a-time rule and pause/cancel/retry are shared. `both` = owned first, then wishlist-only cards, deduped.
- Alerts re-evaluate explicitly after any run with an `ok` fetch (`_after_run`). Snapshot only when an owned card updated: a wishlist-only run must not write a collection snapshot. Alert failures are logged, never fail the run.
- Scheduler keeps staleness-mixed ordering over owned + wishlisted cards (not strictly collection-first): strict ordering would starve the wishlist whenever the collection exceeds `SCHEDULER_FETCH_CAP`. `SCHEDULER_FETCH_WISHLIST=false` opts out. Manual "both" runs are strictly collection first.
- The racy `test_pause_resume_cancel_and_rerun_skips_succeeded` was fixed afterwards: the 3rd fetch is held in flight so cancel always lands before the 4th pair's checkpoint.

## Cost and acquisition type (2026-11-05, roadmap Step 3)
- Granularity: per stack, `acquired.price` = cents per copy (cost = price x qty). Mixed costs = weighted average; the form can take a total for N copies and stores the rounded per-copy average (error <= N/2 cents). Rejected per-copy lots: they break on quantity edits, remove and merge, and need much more UI. Limit: one type per stack, so a stack that mixes Pulled and Purchased copies cannot split P/L ex-pulled exactly.
- Adding copies to an existing stack re-averages the price when both are known and in the same currency; a different type or currency keeps the stack's own value and the add answers `type_conflict: true` (UI warns). Unknown old cost + known new cost takes the new cost.
- No migration: `type` null = "Not set", read-time default, counted as non-pulled. Notes reuse the item-level `notes`.
- P/L bug fixed: stacks without cost used to add their value but 0 cost (real data: 14 of 16 stacks, P/L showed ~+1,159 EUR instead of -32). P/L is now over stacks with cost and value only; the count without cost is shown and links to the "No cost" filter.
- Edit log `collection_edits` keeps full before/after of `acquired` for edit, bulk, merge, import and restore; restore applies a `before` and is itself logged. Never pruned. Alerts do not use cost. Snapshots keep `total_cost` and add ex-pulled / basis / pulled-value / missing-count.
- Export/import: JSON stays v1 (additive), CSV gets `acquired_type`. A `set` import of a file without `type` keeps the type already on the stack and logs an `import` edit when `acquired` changes.

## Collection list: cached valuation, server-side query (2026-11-05, roadmap Step 4)
- Measured first: `valuate()` cold = 190 ms (2000 stacks), 370-560 ms (5000), 760-870 ms (10000), and the old list endpoint paid it on every filter/sort/page click and every Summary/Dashboard call.
- Chosen: cache the whole valuation in process (`valuation_cache`, TTL 60 s + `bump()` from every write path) and run filter / sort / page / totals / facets as pure Python over the cached rows (5-34 ms warm). Rejected: Mongo-side filtering/sorting with valuation only for the page, because value, P/L, price range, needs-price, stale and the filtered totals need the valuation of every matched stack, so it saves nothing and creates a second code path. Rejected: a cache keyed on a Mongo fingerprint (max updated_at/count): price and FX writes touch several collections and `remove` does not stamp `updated_at`, so explicit bumps + TTL are simpler and bounded.
- Limits: in-process, so one uvicorn worker only; a missed bump shows stale values for up to 60 s (`VALUATION_CACHE_TTL=0` turns it off). Tests set the TTL to 0 by default (autouse fixture) because they write straight to Mongo. Cached rows are shared and must stay read-only.
- Filtered totals ride in the list response (`totals`), no separate endpoint: one request, always consistent with the page. Price range filters are per copy (value / quantity), unpriced stacks never match; "price stale" = the headline price's upstream `as_of` is older than `MARKET_MAX_AGE_DAYS`.
- Presets are stored in Mongo (`list_presets`, whitelisted keys, unique per scope + name), not localStorage: the user will also use the phone (Step 5) and a preset should not be lost with a browser. Built-ins are code. View mode (table | grid) is a per-device UI preference, so localStorage.
- Wishlist stays client-side (a few hundred rows at most): search + sort + presets + grid reuse the shared pieces, no pagination until it is needed.

## Phone scanning, slice 1 (2026-11-05, roadmap Step 5)
- **D1 = Tailscale** (user, after the trade-offs). Camera needs https on the phone. Options weighed: mkcert on the LAN (root CA to install on the phone, whose private key sits on the Mac and can mint certificates the phone trusts; port open to everyone on the Wi-Fi), a public tunnel (needs real auth first, rejected), plain http + native camera (no live view, unencrypted Wi-Fi). Tailscale: public Let's Encrypt certificate (nothing to trust on the phone), the Mac is not opened to the Wi-Fi (Caddy binds 127.0.0.1, `tailscale serve` is the only way in), device-level identity via the `Tailscale-User-Login` header Caddy checks. Costs: a Tailscale account and app on both devices; third-party coordination server. Never use Funnel (public).
- **No pairing tokens / QR login.** The tailnet login is the credential; the QR only carries the URL. Rejected: our own device tokens (more code, more state, weaker than a device-authenticated network).
- **Surface kept minimal**: the phone gets 4 scan endpoints, not `/api/collection` or `/api/cards`. `POST /api/scan/add` wraps the normal add so the phone cannot patch, delete, export or import. The DNS-rebinding guard is unchanged: the tailnet host is added to `ALLOWED_HOSTS` by `lan/lan.env` only, and in phone mode only that origin passes the Origin guard. A client cannot fake phone mode (it needs the secret, which only Caddy and the app know); a spoofed gate header is a 403.
- **OCR on the server, local** (Tesseract in the app image), not on the phone: no 10 MB wasm download, faster than phone CPUs, one place to tune. No paid API. Sparse mode on the name band beat one-line mode on synthetic names (8/8 vs 6/8), so both are run and the matcher picks. Accuracy on real card photos is **not measured yet**: tests use synthetic names only. Fallback is always typing the name.
- **Name -> versions**: exact `name_norm` match first (so "Pikachu V" does not collapse into "Pikachu"), fuzzy (difflib 0.75) only when nothing is exact, so a typo is shown as "guess" and never "high". All prints of the best names are listed (max 40 + "Show more"), owned first then newest set. Confidence is a hint; nothing is added without a tap.
- **Edition data gap**: pokemontcg.io has one Base Set Charizard with variant `holofoil`; 1st Edition / Shadowless / Unlimited are not separate. The picker flags sets that have such prints (`EDITION_SETS`) with "check the stamp". No new edition field or price per edition in this slice (prices would be wrong); open question for a later slice.
- **Acquisition remembered, last choice only** (condition, language, cost block) in the phone's localStorage. Duplicate = existing `collection.add` merge (same stack key); the add sheet says "adds one more copy to that stack (N total)".
- **Known limits**: no undo on the phone (slice 2 with batch mode; fix on the laptop), no price fetch triggered by a scanned add (the event carries `card_id`, so a laptop-side follow-up is easy), `apple-touch-icon` is an SVG which iOS ignores (the home screen icon may be a page snapshot), Add to Home Screen storage behaviour on iOS not verified.

## Phone scanning: real-photo OCR (2026-11-07, roadmap Step 5 sub-step 1b)
- **Cause of "Couldn't read a card name"**: fixed top 20 % crop of the whole photo = table, not card. Measured 3/15 on the user's real photos (5 cards, 3 each; HEIC converted with `sips`).
- **Card detection in Pillow only** (no OpenCV/numpy added to the image): Otsu threshold on a 240 px thumbnail, median filter, bounding box; inverted when the frame edge is the lit part (light table); `None` (use the whole image) when the box is under 6 % or over 97 % of the photo.
- **Staged read, early stop**: top band (sparse + one-line), name strip, dark-pixel crops (cuts 90, 60: tesseract fails on a name drawn over busy art such as Chandelure's full art), whole card, whole image. The service stops at the first stage with an exact name of 4+ letters read at 55+ confidence. Typical photo 1-3 s, worst 4 s.
- **Matcher**: text after "Evolves from" is dropped (it names the previous stage and gave Lampent for Chandelure); a matched base name also offers its ex / V / VMAX / VSTAR / GX / BREAK forms because the ex glyph is read as "@x" or not at all. This reverses the slice-1 rule "Charizard ex is a different name, not offered".
- **Result 14/15 (93 %)**; remaining miss is glare on a sleeve. Accuracy test: `tests/test_scan_accuracy.py` reads `tests/private/scan_samples/` (git-ignored, with `labels.json`), skipped when absent, fails below 80 %. Everything else in the suite runs without the private photos.
- **Cost for P/L (user, 2026-11-06)**: a blank or 0 acquisition price means "no cost recorded": the stack's `cost` is `None`, it is excluded from P/L and counted in `cost_missing`. P/L only covers stacks with a cost above 0. Allocating a pulled pack's price over its cards is deferred.
