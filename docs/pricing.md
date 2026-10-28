# Pricing

## Search -> product (fix 2026-10-28)
`resolve.find_product(product_marker=...)`: PriceCharting and Cardmarket redirect a single-hit search straight to the product page, so a search with one hit has no results table. When the fetcher's `final_url` contains the marker (`/game/`, `/Products/Singles/`) it is taken as the product (no candidate scoring). alt.xyz tile titles name the rarity only for some prints ("Hyper Rare"); the rarity filter in `parse_sold` applies only when at least one tile of the same card carries it.

## Sources

| Source id | How | Kind | Notes |
|---|---|---|---|
| `tcgplayer` | embedded in pokemontcg.io payload | market, USD, per variant | low / mid / high / market |
| `cardmarket` | embedded in pokemontcg.io payload | market, EUR, `variant=None` | trend as `market`; `as_of` can be stale |
| `pricecharting` | browser fetcher | market (raw + grades) + sold (graded, per company from listing titles), USD | grade keys: `raw`, `G2`..`G9`, `G9.5` (company-agnostic buckets), `PSA10`/`CGC10`/`BGS10Black`... (10s per company) |
| `cardmarket_web` | browser fetcher (real Chrome) | market (trend, 30d avg) + ask (From), EUR | raw only. Separate id so it never overwrites the `cardmarket` aggregate |
| `altxyz` | browser fetcher | sold, USD, per company grade (`PSA9`, `CGC10`...) | median/low/high of last 10 sales within 90 d, `sample_size` |
| `manual` | `POST /api/cards/{id}/sales` | sold | user-entered comps |

Source ids in the registry (`GET /api/admin/price-sources`) equal the ids stored in `prices.source`.

### Adapter flow (`app/providers/price/`)
`FetcherClient` (providers/fetcher.py) -> `resolve.find_product`: search page -> `match.pick` -> product page -> parser (pure function over HTML, tested on `tests/fixtures/`). A stored/confirmed product URL skips search. Result = `AdapterResult(status, points, sales, candidates, chart)`; fetcher failures become statuses (`login_timeout|blocked|error`), never exceptions.
Matcher: candidate must match number, base name and language, else score 0; set-name token overlap fills the rest; `[Metal]`/`[Jumbo]` style variants are penalised. Accept only if score >= 0.8 and margin >= 0.15 over runner-up, else `needs_match` with ranked candidates (e.g. Cardmarket lists 3 identical "Mew ex (MEW 205)" versions V3/V4/V5 -> user picks).
Matches are stored in `product_matches` (not `cards.external_ids`, which catalog import overwrites): an unambiguous run saves `auto`, `needs_match` saves the candidates, the user picks or pastes a URL via `POST /api/cards/{id}/match/{source}` (validated: https, site host, product path) and that `user` match is never overwritten; `DELETE` resets a wrong one. Stored URL is passed to the adapter as `known_url`.
alt.xyz has no matching step: the search query carries name + number + set + rarity and tiles are filtered by number, name, set tokens and rarity. The list pages client-side (no URL param), so the adapter reads up to `ALTXYZ_MAX_PAGES` (3) pages, newest first, via the fetcher's `click_labels` (`Go to next page` x N-1, one navigation per page, ~1 min per card). It stops early when a page brings no new listing or its oldest sale is older than `ALTXYZ_MAX_AGE_DAYS` (180, ~6 months); sales older than that are dropped (stale sales skew low). Valuation still uses the 90 d `SOLD_WINDOW_DAYS`. Live check 2026-10-28: Mew ex 205 went from ~10 to 28 sales.
PriceCharting sold rows: Japanese listings dropped, grade/company parsed from the title; raw sales are kept as `Sale`s but produce no sold point (condition unknown).

Aggregate = provider-computed number; sold = individual completed sale. UI labels aggregate prices "Market price (aggregate)" and shows sold min/avg/max when sales exist.

## Scraped sources: findings (spikes, card Mew ex 151 #205, last verified 2026-10-27)

Fixtures in `tests/fixtures/{pricecharting,cardmarket,altxyz}/`. Parsers are tested against them; re-capture when a site changes.

- **PriceCharting**: works headless, no login. Search `/search-products?type=prices&q=...` -> `table#games_table tr[data-product]`. Product page `table#price_data` (ungraded, G7, G8, G9, G9.5, PSA 10) and `#full-prices` rows. **Grades are company-agnostic buckets** (1-2, 3..9, 9.5); only 10s are per company (TAG, ACE, SGC, CGC, PSA, BGS, BGS Black, CGC Pristine). A PSA 9 maps to the Grade 9 bucket, flagged company-agnostic. Sold lists in hidden `div.completed-auctions-*` (rows `tr#ebay-<id>|tcgplayer-<id>`, date, title with grader+grade, USD); grades 1-6 and non-PSA 10s have price only. `VGPC.chart_data` = monthly series (~38 points) usable as history seed.
- **Cardmarket**: needs real Chrome via CDP (Cloudflare; Chromium gets 403 / "Just a moment..."). No login. Product page: From, Price Trend, 30d/7d/1d averages (EUR), offer rows. **No sold list, no grades** -> kinds `market` and `ask` only. Search returns several versions (V3/V4/V5, Japanese prints): match by set + number + language.
- **alt.xyz**: SPA, headless and anonymous OK, needs JS (~5 s). Sold list: open `/browse?query=...`, toggle "Sold listings" (URL becomes `...&soldListings=true&sortBy=newest_first`; loading that URL directly can time out). 10-15 tiles/page; pagination is MUI buttons with `aria-label="Go to next page"` (disabled on page 1), no `?page=` support. Tile: `Sold • <date>`, set title, card, `<COMPANY> <grade>`, price USD, sale type; link `/itm/<uuid>/sold` (uuid = dedupe key). **Per-company, per-grade sold prices** (fills PriceCharting's bucket gap). Results mix set prints: filter by set name. Active listings (no toggle) = `ask`. Undocumented GraphQL backend deliberately unused.

## Data model v2 (observation log)

`prices` row = one observation: `{card_id, variant|None, source, kind: sold|market|ask, grade_key ('raw'|'PSA9'|...), currency, observed_on, as_of, low, avg, median, high, market, sample_size, url, fetched_at}`.
Unique key `(card_id, variant, source, kind, grade_key, observed_on)`; `observed_on` = UTC date of *our* fetch, `as_of` = upstream timestamp (nullable, may be stale). Same-day re-fetch overwrites; a new day adds a point. Upstream 0 = no data -> `None`.
`cards.latest_price[source][kind][grade_slot][variant_slot]` holds the newest value (`variant_slot` `_` = no variant; `grade_slot` replaces `.` with `_`). `cards.price_base` = headline raw price (cardmarket, else tcgplayer). `cards.price_schema = 2`.
`variants` is `[]` when the card has no real variants; `CollectionIn.variant` is optional (None). Migration `app/db/migrate_prices_v2.py` runs idempotently on boot. Source registry: `app/providers/price/__init__.py` (`GET /api/admin/price-sources`).

### Scraped fetch job (`services/price_fetch.py`)
- Sequential card x source, one `price_fetch` job at a time. A pair with a `fetch_log` `ok` younger than 24h is skipped (`skipped_cached`) unless `force`. `needs_match` / `not_found` are reported in job stats, not failures.
- `login_timeout` / `blocked`: remaining cards of that site are skipped for the run (`skipped_site`). `error` + fetcher unreachable aborts the job (`error`). Job is `partial` when any pair failed.
- While an adapter waits on the user's login, job stats `waiting_login` lists the source ids (polled from the fetcher `/status`; `cardmarket_web` = fetcher site `cardmarket`).
- Storage: observations as above (sold `as_of` dates stored as UTC-midnight datetimes); `latest_price` is merged per slot (`latest_price.<source>.<kind>.<grade>.<variant>`). The catalog refresh only rewrites the `tcgplayer` / `cardmarket` sub-trees, so scraped values survive it. Scraped sources never change `price_base`.
- Sold listings: persisted in `sales` for `ok` results (a `not_found` result stores nothing), upserted on `(card_id, source, listing_id)` (unique partial index `sales_listing_key`; manual sales have no `listing_id`). Fields: `grade_key`, `price` (cents), `currency`, `title`, `sold_at` (UTC midnight), `kind "sold"`, `created_by "scraper"`, `first_seen`, `fetched_at`. They feed `sales` / `sales_stats` in `GET /api/cards/{id}`.
- Chart seed: PriceCharting's monthly ungraded series is inserted into `prices` as `kind market, grade_key raw` observations with `seed: true` (`$setOnInsert`: an existing observation of that day is never overwritten). A later real observation of the same key replaces the row and drops `seed`. Seeds never touch `latest_price` / `price_base`.
- Job stats also carry `sales_new` (new `sales` rows) and `seeded` (new seed observations).

## Price matrix (`GET /api/cards/{id}/price-matrix`)

One cell per (grade, source): newest observation day, then sold > market > ask, then the card's first variant. Rows = fixed baseline (`raw`, PSA/BGS/CGC 1-10) plus every grade stored for the card, sorted `raw`, company-agnostic buckets `G9.5..G1`, then per company (PSA, BGS, CGC, others) by grade descending with company 10 variants (`BGS10Black`, `CGC10Pristine`) after the plain 10. `graders` lists the companies present. Cell value = `market`, else `median`, else `avg`; only `ask` cells fall back to `low` (Cardmarket "From"). Cells carry `fetched_at`, `seed` (history seed, not a real observation) and `url`.

## Valuation

`services/valuation.py` (`resolve_item`, pure) picks one price per collection item; `collection.valuate` is the only entry point (collection list/summary, dashboard, snapshots all use it).

Grade chain, first hit wins (raw items: step 1 only):
1. **exact** grade (`PSA9`).
2. **bucket** `G9` (PriceCharting, company-agnostic; none for 10s). Not exact.
3. **lower**: nearest lower grade of the same company that has data. Not exact.
4. **raw_fallback**: raw market price. Not exact.
5. **none**: unpriced, value `None` (never 0).

Only `exact` is shown without `≈`. Every other match sets `estimated`; the UI says why (bucket / lower grade / raw fallback / variant fallback).

Within one grade (D-A): **sold** if >= `SOLD_MIN_SALES` (3) sales in the last `SOLD_WINDOW_DAYS` (90): median of the last `SOLD_SAMPLE` (10), pooled across sources in `sales` and converted to base currency; else aggregate **market** by `PREFERRED_SOURCES` (default `pricecharting > tcgplayer > cardmarket_web > cardmarket > altxyz`, then any other source; Phase 5: scraped `cardmarket_web` is unverified per product version and the catalog `cardmarket` figure can be months stale, so they rank below pricecharting/tcgplayer); else **thin sold** (1-2 sales, or a sold point in `latest_price`), flagged `thin` with the sale count. All three are env settings (`app/config.py`), no UI.
- Stale guard: a market point whose upstream `as_of` is older than `MARKET_MAX_AGE_DAYS` (180) only counts when no fresher source has that grade. Scraped points have no `as_of` (dated by our fetch) and count as fresh.
- Ask prices (Cardmarket "From") are never used: a listing floor is not a value.
- Scraped raw sales have unknown condition, so they never value a raw item or a raw fallback; only `manual` sales do.
- Variant: item variant, else the source's no-variant price, else the first variant (flagged estimated).
- Item value = quantity x price, converted to base currency (FX from frankfurter.dev, cached daily). Row fields: `value`, `price_kind`, `source`, `match`, `grade_key_used`, `estimated`, `thin`, `sample_size`; `values[source]` / `sources[source]` = result when only that source is used (own fallback chain; carries `thin` and `sample_size`). `valuate(db, as_of=date)` revalues the same items at a past date from `prices.observed_on <= date` (`pricing.latest_as_of`) and sales in the window before it.
- Cost = acquired price converted at today's rate. P/L = value - cost (null when no cost recorded).
- Raw headline `cards.price_base` is unchanged (cardmarket, else tcgplayer); valuation of raw items follows `PREFERRED_SOURCES`, so it can differ from it.

## Source comparison (Phase 5b)

Collection (expand a row), CardDetail ("Compare sources": one raw copy + each owned slab, `GET /api/cards/{id}/compare?company=&grade=&variant=`) and Dashboard (source table from `GET /api/collection/summary` `by_source`) show every source side by side. Per source: value, kind, match, thin, data age (`observed_on` = our fetch day, `as_of` = upstream date; sold: newest sale), `stale` (catalog `as_of` older than `MARKET_MAX_AGE_DAYS`; shown struck through), and the matched print (`product` in `GET /api/cards/{id}/match`: slug + Cardmarket version). `headline_rule` says why the headline source won. `spread` = median/min/max plus `outliers` (> `OUTLIER_PCT` = 40 % from the median, >= 3 like-for-like sources). Dashboard `vs_headline_pct` compares a source with the headline over the same items only. `latest_price` entries carry `observed_on` (older ones fill in on the next fetch / refresh).

## Snapshots

Taken after each refresh (or `POST /api/admin/snapshot`). One per UTC date. No backfill possible: history starts at the first snapshot. Fields: `totals_by_source` (value via that source alone), `total_value` (the headline valuation), `value_kind_breakdown` (sum per sold/market), `estimated_count`, `weak_by_source` (any item valued thin or not exact via that source; the chart draws a hollow dot). Snapshots before Phase 5 lack `weak_by_source`.

## Movers (`services/movers.py`)

Each owned item valued now vs N days ago with the same resolver (graded-aware, sold-based). Only items priced the same way at both ends count (same price kind, grade match and grade key): a changed fallback is a data gap, not a move. Past values use only what the observation log and sales held at that date; scraped sales are dated by `sold_at`, so a sale we fetched later still counts in the past window. Snapshots before Phase 4 valued slabs at raw price and lack `total_value`; the dashboard change % only compares snapshots that have it.

## Alerts (`services/alerts.py`, Phase 7)

Rules on one stack, one card (all its stacks) or the collection total: `above|below X` (EUR cents) or `up|down N% over D days`, optional price-kind filter (`sold|market|any`). Evaluated at the end of `take_snapshot`, which every refresh, scraped fetch and the scheduled snapshot already call, using the same `valuate()` result as the screens (so an alert value equals the Collection value). % rules compare with `valuate(as_of=now-D)` and only count items that pass `movers.comparable`.
- One event per crossing: condition true and rule `triggered=false` -> atomic flip + one `alert_events` row; condition false -> re-armed. Unknown (unpriced, estimated, wrong kind, not comparable) leaves the state alone.
- Estimated values (bucket / lower / raw fallback) do not alert unless the rule has `include_estimated`. Thin sold values do alert and the event says so.
- Totals / card scope sum only items that are usable for the rule (priced, not estimated, kind matches).
- Inbox also receives `system` items (deduped per day by key): scheduled fetch skipped because the fetcher is down, or a site needing login / challenge.
- Failure isolation: an exception in alert evaluation is logged and never fails the snapshot.

## Scheduled fetches
With `SCHEDULER_ENABLED`, a daily `price_fetch` covers up to `SCHEDULER_FETCH_CAP` owned cards (stalest first), with the usual 24 h cache-skip and unattended fetcher mode (see decisions.md, Phase 6). Sites that need a login yield no new points that day.

## Unpriced cards
Some sets/cards have no price block in the pokemontcg.io payload (e.g. `me55`, `me5`, `me2pt5`, `mcd*`, `tk*`), so they stay unpriced (`price_base = None`, shown as "no price"). That is a source gap, not an import failure; only another source can fill it. Settings shows priced/total per set.
