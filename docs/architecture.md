# Architecture

Browser (Vite React SPA :5180) -> FastAPI (:8100) -> MongoDB 7 (compose network only, auth on). External: pokemontcg.io (catalog + prices), frankfurter.dev (FX). Scraped price sites are reached only through the host-Mac **fetcher** (below).

## Backend layering

`api/` (thin routers) -> `services/` (logic) -> `providers/` (only place that does HTTP) + `db/`.

| Module | Role |
|---|---|
| `providers/catalog/pokemontcg.py` | httpx + tenacity retry on 429/5xx, maps payload to card/set docs, extracts price points |
| `services/catalog_import.py` | per-set import (all / chosen sets / retry of failed), upsert by `_id`, job logging, failed-set isolation |
| `services/portability.py` | collection export (JSON v1 lossless, CSV flat) and import (validates via `CollectionIn`, upsert on `stack_key`, per-row errors) |
| `services/sets.py` | sets with imported / priced card counts |
| `services/search.py` | builds Mongo query from `q` + filters |
| `services/collection.py` | add/stack-merge, `valuate` (loads cards + 90 d sales, per-source and best value) |
| `services/valuation.py` | pure per-item price resolver: grade chain exact > bucket > lower > raw fallback, sold (D-A) > market > thin sold |
| `services/pricing.py` | stores price points, denormalises `latest_price` / `price_base` on cards |
| `services/fx.py` | daily FX cache in `fx_rates`, fallback to last stored rate |
| `services/movers.py` | top movers: `valuate` now vs `as_of` N days ago, comparable items only |
| `services/snapshots.py` | daily collection snapshot (idempotent per UTC date); ends by calling `alerts.evaluate` with the same valuation |
| `services/alerts.py` | price alert rules + state machine (`alerts`, `alert_events`), system inbox items, unread count |
| `services/refresh.py` | price refresh job (collection, all, or chosen sets) then snapshot |
| `providers/fetcher.py`, `providers/price/{pricecharting,cardmarket,altxyz,match,resolve}.py` | fetcher HTTP client; scraped-site adapters + matcher (see pricing.md) |
| `services/price_fetch.py` | on-demand scraped fetch job `price_fetch` (cards / sets / owned x sources): adapters -> `prices` + `latest_price`, records matches, `fetch_log` (`{card_id}\|{source}`: status, detail, url, fetched_at), snapshot at end. Endpoints `POST /api/admin/prices/fetch`, `POST /api/cards/{id}/fetch-prices` (202; 422 bad target/source; 503 fetcher down; 409 running) |
| `services/sales.py` | `store_sales` (scraped sold listings, dedupe on listing id), `store_chart_seed` (PriceCharting monthly history as `seed` observations) |
| `services/matching.py` | persisted card -> product URL per scraped source (`product_matches`), URL validation, user/auto precedence |
| `jobs/scheduler.py` | APScheduler, only if `SCHEDULER_ENABLED`: tasks `daily_refresh`, `daily_fetch` (scraped, unattended, capped), `daily_snapshot`, `weekly_catalog`, each via `run_task` (failures and busy job types are logged, never propagate). Boot `catch_up` runs overdue tasks once, in the background. `jobs` rows carry `trigger` = `manual`\|`scheduler`\|`catchup`; a scheduled fetch with the fetcher down is a `skipped` row |

Long jobs run as asyncio tasks; state is persisted in the `jobs` collection (UI polls `/api/admin/jobs`). One `running` job per type: API returns 409, and a partial unique index on `jobs.type` (status=running) is the race-free backstop. Orphaned `running` jobs are marked `interrupted` on boot.

## Fetcher (host Mac, `fetcher/`)

Separate small FastAPI service, not in docker-compose, bound to `127.0.0.1:8110`. The app reaches it at `FETCHER_URL` (default `http://host.docker.internal:8110`). The app never launches browsers; the fetcher never touches Mongo.

Engine: real Google Chrome started by the fetcher with `--remote-debugging-port` and a dedicated profile (`~/.moc-fetcher/profile`, never the user's main profile), driven by Playwright `connect_over_cdp`. Browser starts on first request and closes after an idle timeout or `POST /close`.

- `POST /fetch/{site}` `{url, wait_selector?, click_text?, wait_ms?, timeout_s?}` -> `{status: ok|login_timeout|blocked|error, final_url, title, html, detail}`. Sites: `pricecharting`, `cardmarket`, `altxyz`; URL host must belong to the site (no open proxy).
- `click_text` (optional): clicked after load / `wait_selector` (alt.xyz "Sold listings" toggle), after a short hydrate delay.
- `GET /status` -> browser up/down, per-site `idle|fetching|waiting_login`. `POST /close`, `GET /health`.
- Per-site limiter: concurrency 1, min interval 3-5 s (+jitter).
- Flow: always try anonymous first. On a login wall or Cloudflare challenge the tab is brought to front on the site's page, state `waiting_login`, polled until cleared or `LOGIN_TIMEOUT_S`; credentials are never read. Screenshot saved on failure.

## Data model (collections)

- `cards`: `_id "pokemon:base1-4"`, tcg, name, `name_norm`, `search_text`, set{}, images, variants[], `latest_price{source{variant{market,low,avg,high,currency,as_of}}}`, `price_base` (cents, base currency). Indexes: text, name_norm, (tcg,set,number), rarity, types.
- `sets`: one per set.
- `collection_items`: one doc per stack, unique `stack_key` = card|variant|language|condition|grader|grade|cert. Add = `$inc quantity`; remove to 0 deletes.
- `prices`: unique (card, variant, source, kind, grade_key, as_of); `kind` market | sold | listing_low. Re-refresh same day = same doc.
- `sales`: sold records, manual (`POST /cards/{id}/sales`) and scraped (unique `(card_id, source, listing_id)` when `listing_id` is set); stats: last 10 within 90 days per source+grade.
- `collection_snapshots`: unique per date; `totals_by_source`, `total_value`, `value_kind_breakdown`, `estimated_count`, cost, counts, unpriced counts, breakdowns (pre-Phase-4 docs lack the first three).
- `product_matches`: `_id "{card_id}|{source}"`, `url`, `confirmed_by` auto|user|null, pending `candidates`; only `pricecharting`, `cardmarket_web`.
- `alerts`: rule `{scope stack|card|total, item_id|card_id, op above|below|up_pct|down_pct, threshold (cents or %), days, kind, include_estimated, enabled, triggered, last_value, last_pct, last_eval, label}`.
- `alert_events`: `type alert|system`, rule text, card, `value/prev/pct`, kind/match/thin/estimated, `fired_at`, `read`; system items carry a unique `key` (one per day per reason). Index `(read, fired_at)`.
- `fx_rates`, `jobs`.

Money: integer cents + currency everywhere. Missing price = `null`, never 0.

## API (prefix `/api`; Swagger at `/docs`)

`GET /cards` (incl. `has_price`), `/cards/{id}`, `/cards/{id}/prices`, `POST /cards/{id}/sales`, `GET /cards/{id}/price-matrix` (grades/graders derived from stored rows), `GET /cards/{id}/fetch-status` (last scraped-fetch outcome per source), `GET /cards/{id}/match`, `POST|DELETE /cards/{id}/match/{source}` (confirm / reset product URL), `GET /sets` (`?with_stats=true`), `/filters`;
`/collection` (POST add, GET list with per-item `value/price_kind/source/match/estimated/sources`, `/summary` with `value_by_kind`, PATCH/DELETE `/{id}`, POST `/{id}/remove`);
`/dashboard/history|breakdown|movers`;
`/alerts` (GET list, POST create, PATCH/DELETE `/{id}`), `/alerts/events` (`?unread=`), POST `/alerts/events/read` (`{ids}` or all), `/alerts/unread-count`, POST `/alerts/evaluate`;
`/admin/catalog/import` (`?sets=` repeatable), `/admin/catalog/import/retry-failed`, `/admin/prices/refresh` (`?scope=&sets=`), `/admin/snapshot`, `/admin/jobs`, `/admin/status` (incl. `scheduler.jobs[].next_run`), `/admin/fetcher-status` (`{up, ...}`; 200 even when the fetcher is down), `/admin/prices/fetch`.
Health: `/health`, `/health/ready` (pings Mongo).

## Config (`.env`, see `.env.example`)

`MONGO_ROOT_USER/PASSWORD`, `BASE_CURRENCY`, `POKEMONTCG_API_KEY` (optional), `SCHEDULER_ENABLED`, `PRICE_REFRESH_CRON` (`0 4 * * *`), `PRICE_FETCH_CRON` (`30 4 * * *`), `SNAPSHOT_CRON` (`0 6 * * *`), `CATALOG_IMPORT_CRON` (`0 3 * * 0`), `SCHEDULER_FETCH_CAP` (300), `FETCHER_URL`, valuation rules `SOLD_MIN_SALES` (3), `SOLD_WINDOW_DAYS` (90), `SOLD_SAMPLE` (10), `PREFERRED_SOURCES` (comma list), `MARKET_MAX_AGE_DAYS` (180). `PRICECHARTING_TOKEN` is unused (no paid API).

## Frontend

Vite + React 18 + TS + react-router 6 + TanStack Query + Tailwind (dark via OS) + Recharts. All backend calls in `web/src/lib/api.ts`. One colour per price source in `lib/colors.ts`.

## Security posture

Local single-user, no auth. API bound to 127.0.0.1, CORS limited to the web origin, Mongo not exposed on host, security headers set. Secrets only in `.env` (gitignored). Add auth before any deployment.

## Demo database

`owncollection_demo` on the same Mongo server holds seeded items for UI checks; the real `owncollection` is only read. `docker compose run --rm app python -m app.scripts.demo_db create|status|drop`; run the app on it with `docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d app`, back with `docker compose up -d app`. Tests never use it (throwaway `moc_test_*` DBs).

## Docker

`moc-mongo` (volume `moc_mongo_data`), `moc-app` (`./app` mounted, no reload), `moc-web` (node:20, vite dev, deps in volume).
