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
- **npm audit (8 findings, all fixes are semver-major):** `vitest`/`@vitest/mocker`/`tinypool` (incl. the 2 critical "prototype pollution -> RCE" in tinypool worker options) and `vite`/`esbuild` (dev server readable by any website) are **dev-only**: never in the built bundle, the dev server is published on 127.0.0.1 only, and the exploit paths need attacker-controlled test config or a visit to the dev server while it runs. `react-router`/`react-router-dom` is shipped, but the advisories are an open redirect via backslash in user-supplied `<Link>`/`navigate` targets (the app has none: all targets are literals or ids) and SSR hydration (`deserializeErrors`, no SSR here). Fix needs vitest 4 / vite 8 / router 7, each a breaking migration of tooling that works; deferred until the next planned toolchain bump. Re-run `npm audit` then.
- Web container has a healthcheck (wget on :5180, 120 s start period for the first `npm install`). No prod nginx image: nothing is deployed.

## Phase 8: leftovers (2026-10-28, defaults by me, change on objection)
- **Alert prune**: only READ `alert_events` older than `ALERT_EVENTS_KEEP_DAYS` (90, 0 = off) are deleted, by a scheduler task `daily_prune` (06:30, `ALERT_PRUNE_CRON`). Not run inside `evaluate` (price-update path stays free of housekeeping) and not caught up at boot. Rule state (`triggered`) lives on the rule, so deleting events never re-fires anything. Market data (`prices`, `sales`, snapshots) is untouched.
- **alt.xyz paging**: `?page=N` is ignored by the site (client-side pagination), so the fetcher got `click_labels`. Adapter reads <= `ALTXYZ_MAX_PAGES` (3) pages and stops when the oldest sale on a page is older than `ALTXYZ_MAX_AGE_DAYS` (180); older sales are dropped. User guidance: only the last ~3-6 months of sold listings count, older ones skew low. Valuation window stays 90 d. PriceCharting / Cardmarket adapters unchanged (they read no per-sale list beyond what the page shows; their `sold_points` already use the 90 d window).
- Cost: each extra page is another navigation, so alt.xyz takes ~1 min per card (was ~15 s). A scheduled fetch of 300 cards is long: lower `ALTXYZ_MAX_PAGES` if that matters. Possible later optimisation: one navigation returning every page's HTML.
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
- Legacy classes `.btn`, `.btn-ghost`, `.input`, `.card` stay (re-implemented on the tokens) so unrestyled pages follow the theme; remove them when the last page is migrated.
- Restyle order (user): Collection, Dashboard, Alerts (done: guided sentence form, `Combobox` picker over `/api/collection?q=&page=` so no 200 cap, no backend change; `?stack=` label resolved from one list call; Inbox badge says "unread" so it does not clash with the Rules "N new" label; jsdom polyfills for Radix Select in `test/setup.ts`), Settings, then PriceMatrix and the price chart (card detail). Search + Card page shell are done.
- Collection restyle (2026-10-29): `GET /api/collection` gains `order=asc|desc` and sorts `cost|pl|qty|set` (plus `added|value|name`); rows with no value for the sort key (None) always go last in either direction; each row has `pl` (value - cost, None if either missing). Collection UI state (filters, sort, page, size) lives in the URL. Value chart reuses `/api/dashboard/history` (legacy snapshots hidden). New shared kit parts: `Table/SortTh`, `Pagination`, `Drawer` (Radix Dialog; first use of `dialog`). Page size is not capped by the old 50 anymore: user picks 25-200.
- Dashboard restyle (2026-10-29): purpose split. **Collection = inventory** (find / edit stacks, fix missing prices), **Dashboard = insight** (how it is doing, what changed). Dashboard = KPI strip (value, 30d change, P/L, cost), `ValueChart full` (adds 7d range + compare-sources toggle), `BarList` composition (top 10 + Other, CSS bars so long set names are not cut), top holdings (`/api/collection?sort=value&order=desc&page_size=8`, no new endpoint), movers up/down, data-quality card (sold-based %, estimated / needs price / no data, Fetch missing prices via the shared `usePriceFetchJob`), source comparison collapsed. Reliability and unpriced counts moved off the KPI row. No backend change.
