# Architecture

Browser (Vite React SPA :5180) -> FastAPI (:8100) -> MongoDB 7 (compose network only, auth on). External: pokemontcg.io (catalog + prices), frankfurter.dev (FX).

## Backend layering

`api/` (thin routers) -> `services/` (logic) -> `providers/` (only place that does HTTP) + `db/`.

| Module | Role |
|---|---|
| `providers/catalog/pokemontcg.py` | httpx + tenacity retry on 429/5xx, maps payload to card/set docs, extracts price points |
| `services/catalog_import.py` | per-set import (all / chosen sets / retry of failed), upsert by `_id`, job logging, failed-set isolation |
| `services/sets.py` | sets with imported / priced card counts |
| `services/search.py` | builds Mongo query from `q` + filters |
| `services/collection.py` | add/stack-merge, valuation per source |
| `services/pricing.py` | stores price points, denormalises `latest_price` / `price_base` on cards |
| `services/fx.py` | daily FX cache in `fx_rates`, fallback to last stored rate |
| `services/snapshots.py` | daily collection snapshot (idempotent per UTC date) |
| `services/refresh.py` | price refresh job (collection, all, or chosen sets) then snapshot |
| `jobs/scheduler.py` | APScheduler daily cron, only if `SCHEDULER_ENABLED` |

Long jobs run as asyncio tasks; state is persisted in the `jobs` collection (UI polls `/api/admin/jobs`). One `running` job per type: API returns 409, and a partial unique index on `jobs.type` (status=running) is the race-free backstop. Orphaned `running` jobs are marked `interrupted` on boot.

## Data model (collections)

- `cards`: `_id "pokemon:base1-4"`, tcg, name, `name_norm`, `search_text`, set{}, images, variants[], `latest_price{source{variant{market,low,avg,high,currency,as_of}}}`, `price_base` (cents, base currency). Indexes: text, name_norm, (tcg,set,number), rarity, types.
- `sets`: one per set.
- `collection_items`: one doc per stack, unique `stack_key` = card|variant|language|condition|grader|grade|cert. Add = `$inc quantity`; remove to 0 deletes.
- `prices`: unique (card, variant, source, kind, grade_key, as_of); `kind` market | sold | listing_low. Re-refresh same day = same doc.
- `sales`: manual sold records (stats: last 10 within 90 days per source+grade).
- `collection_snapshots`: unique per date; totals per source, cost, counts, unpriced counts, breakdowns.
- `fx_rates`, `jobs`.

Money: integer cents + currency everywhere. Missing price = `null`, never 0.

## API (prefix `/api`; Swagger at `/docs`)

`GET /cards` (incl. `has_price`), `/cards/{id}`, `/cards/{id}/prices`, `POST /cards/{id}/sales`, `GET /sets` (`?with_stats=true`), `/filters`;
`/collection` (POST add, GET list, `/summary`, PATCH/DELETE `/{id}`, POST `/{id}/remove`);
`/dashboard/history|breakdown|movers`;
`/admin/catalog/import` (`?sets=` repeatable), `/admin/catalog/import/retry-failed`, `/admin/prices/refresh` (`?scope=&sets=`), `/admin/snapshot`, `/admin/jobs`, `/admin/status`.
Health: `/health`, `/health/ready` (pings Mongo).

## Config (`.env`, see `.env.example`)

`MONGO_ROOT_USER/PASSWORD`, `BASE_CURRENCY`, `POKEMONTCG_API_KEY` (optional), `PRICECHARTING_TOKEN` (provider disabled when empty), `SCHEDULER_ENABLED`, `PRICE_REFRESH_CRON`.

## Frontend

Vite + React 18 + TS + react-router 6 + TanStack Query + Tailwind (dark via OS) + Recharts. All backend calls in `web/src/lib/api.ts`. One colour per price source in `lib/colors.ts`.

## Security posture

Local single-user, no auth. API bound to 127.0.0.1, CORS limited to the web origin, Mongo not exposed on host, security headers set. Secrets only in `.env` (gitignored). Add auth before any deployment.

## Docker

`moc-mongo` (volume `moc_mongo_data`), `moc-app` (`./app` mounted, no reload), `moc-web` (node:20, vite dev, deps in volume).
