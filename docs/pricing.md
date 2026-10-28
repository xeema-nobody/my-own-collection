# Pricing

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
alt.xyz has no matching step: the search query carries name + number + set + rarity and tiles are filtered by number, name, set tokens and rarity. Only the first page (~10-15 tiles) is read, so sold stats are thin for rarely traded grades.
PriceCharting sold rows: Japanese listings dropped, grade/company parsed from the title; raw sales are kept as `Sale`s but produce no sold point (condition unknown).

Aggregate = provider-computed number; sold = individual completed sale. UI labels aggregate prices "Market price (aggregate)" and shows sold min/avg/max when sales exist.

## Scraped sources: findings (spikes, card Mew ex 151 #205, last verified 2026-10-27)

Fixtures in `tests/fixtures/{pricecharting,cardmarket,altxyz}/`. Parsers are tested against them; re-capture when a site changes.

- **PriceCharting**: works headless, no login. Search `/search-products?type=prices&q=...` -> `table#games_table tr[data-product]`. Product page `table#price_data` (ungraded, G7, G8, G9, G9.5, PSA 10) and `#full-prices` rows. **Grades are company-agnostic buckets** (1-2, 3..9, 9.5); only 10s are per company (TAG, ACE, SGC, CGC, PSA, BGS, BGS Black, CGC Pristine). A PSA 9 maps to the Grade 9 bucket, flagged company-agnostic. Sold lists in hidden `div.completed-auctions-*` (rows `tr#ebay-<id>|tcgplayer-<id>`, date, title with grader+grade, USD); grades 1-6 and non-PSA 10s have price only. `VGPC.chart_data` = monthly series (~38 points) usable as history seed.
- **Cardmarket**: needs real Chrome via CDP (Cloudflare; Chromium gets 403 / "Just a moment..."). No login. Product page: From, Price Trend, 30d/7d/1d averages (EUR), offer rows. **No sold list, no grades** -> kinds `market` and `ask` only. Search returns several versions (V3/V4/V5, Japanese prints): match by set + number + language.
- **alt.xyz**: SPA, headless and anonymous OK, needs JS (~5 s). Sold list: open `/browse?query=...`, toggle "Sold listings" (URL becomes `...&soldListings=true&sortBy=newest_first`; loading that URL directly can time out). 15 tiles/page. Tile: `Sold • <date>`, set title, card, `<COMPANY> <grade>`, price USD, sale type; link `/itm/<uuid>/sold` (uuid = dedupe key). **Per-company, per-grade sold prices** (fills PriceCharting's bucket gap). Results mix set prints: filter by set name. Active listings (no toggle) = `ask`. Undocumented GraphQL backend deliberately unused.

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

- Item value = quantity x source market price, converted to base currency (FX from frankfurter.dev, cached daily).
- tcgplayer: matching variant, else first variant (flagged estimated). cardmarket: single price for any variant.
- Graded items have no graded prices yet: valued at raw price, flagged estimated (`≈`).
- Headline value = cardmarket if present, else tcgplayer. Unpriced items counted, not valued at 0.
- Cost = acquired price converted at today's rate. P/L = value - cost (null when no cost recorded).

## Snapshots

Taken after each refresh (or `POST /api/admin/snapshot`). One per UTC date. No backfill possible: history starts at the first snapshot.

## Unpriced cards
Some sets/cards have no price block in the pokemontcg.io payload (e.g. `me55`, `me5`, `me2pt5`, `mcd*`, `tk*`), so they stay unpriced (`price_base = None`, shown as "no price"). That is a source gap, not an import failure; only another source can fill it. Settings shows priced/total per set.
