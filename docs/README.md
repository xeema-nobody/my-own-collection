# my-own-collection

Personal, local, single-user web app to administer trading-card collections. Pokémon TCG first; schema is generic (`tcg` field) so other TCGs plug in via a new catalog provider.

## Overview

**Objective**: know what a card collection is worth, from trustworthy data, without any cloud service. Own catalog and own price history in a local MongoDB; real sold prices (not asking prices) drive the value.

**Shape**: Vite React SPA (:5180) -> FastAPI (:8100) -> MongoDB 7, all in docker compose, bound to 127.0.0.1, single user, no auth. One small extra service, the **fetcher**, runs on the host Mac and drives real Chrome to read PriceCharting, Cardmarket and alt.xyz (Cloudflare blocks anything else); the app only talks to it over localhost HTTP. Details: `architecture.md`.

**Data flow**: catalog import (pokemontcg.io) -> cards/sets -> you add stacks to the collection -> price refresh (API aggregates) and scraped fetch (sold listings) -> valuation (sold-based when >=3 sales in 90 d, else market) -> daily snapshot -> dashboard, movers, alerts. Rules: `pricing.md`.

**Status** (2026-10-28): phases 0-8 done (catalog, collection, price model, scraped fetch, graded valuation, dashboard, source compare, scheduler, alerts, hardening). Scheduler and backup schedule are built but not yet switched on. Next work: `roadmap.md`.

## Features

- **Catalog**: cards and sets imported from an external API into own MongoDB. Idempotent (re-import is safe).
- **Search**: free text over name / set / number / types / rarity / rules text (accent-insensitive, multi-token AND, `4/102`, `#4`, `base1-4`). Filters: set, type, rarity, supertype, price range, has price (yes/no), owned only. Unpriced cards sort last on price ascending. Sort by release, name, price. URL-synced filters.
- **Card detail**: image, metadata, prices per source, price history chart, sold-sales stats, owned stacks (+/−/remove), add-to-collection form.
- **Collection** (graded copies without a graded price are shown as "needs price" and left out of Value/P-L; "Fetch missing prices" fetches just those cards; adding a card from its page starts a price fetch automatically, best effort):  stacks of identical copies (card + variant + language + condition or grading). Raw copies need a condition; graded copies need grader + grade (optional cert, which makes the slab unique). Purchase price/date/notes. Page = KPI strip, value-over-time chart (daily snapshots, 30d/90d/1y/all), filters (search, type, condition, language, needs price; Select/Checkbox kit components), sortable columns (card, set, qty, value, cost, P/L; unvalued stacks always last), real pagination (25-200 per page). Filters, sort and page live in the URL (`/collection?sort=pl&page=2`). Row click or the chevron opens a details drawer (value, why estimated, source compare); the bell links to `/alerts?stack=<id>` which prefills the alert form. Graded copies are valued at their own grade's price (sold median when >=3 sales in 90 d, else market); each value shows a `sold`/`market` badge and source, and `≈` with a reason when it is a fallback (grade bucket, lower grade, raw price) - see `pricing.md`.
- **Prices**: aggregate market prices from TCGplayer (USD) and Cardmarket (EUR), converted to the base currency (default EUR). Manual sale entry for sources without an API (e.g. alt.xyz).
- **Dashboard** (insight; Collection is the inventory): KPI strip (value, 30d change, P/L with % vs cost, cost), value-over-time chart (7d..all; "Compare sources" adds one line per source, hollow dots = that source valued something thin or not exact), "Where the value is" ranked bars by set / rarity / condition / language / TCG (top 10 + Other, with % share), top holdings (8 most valuable stacks), top movers up/down (sold-based, graded-aware; need the same kind of price now and N days ago), a data-quality card (% sold-based, estimated / needs graded price / no data counts, "Fetch missing prices"), and a collapsed per-source comparison table. 30d change only compares snapshots taken since graded valuation.
- **Settings** (tabs Catalog | Prices | Automation | Data | Jobs, `?tab=`): Catalog = actions split into "Selected sets" and "Everything" (Import all / Refresh all ask for confirmation), searchable set table grouped by series with filter chips (not imported / incomplete / no prices) and per-series select-all; Prices = one "Price fetching" card (scope selected sets / owned / missing prices, source chips, force) plus the price-source table; Automation = scheduler, fetcher, next runs; Data = export, drop-zone import; Jobs = readable rows (duration, one-line summary, expandable raw stats, type filter, last 20). Catalog notes: set picker (per-set priced/total) to import or refresh prices for chosen sets, "Retry incomplete" for sets with fewer cards than upstream `total` (shown red as "N missing") or that failed the last full import, provider status, job log. One job per type at a time (second start returns 409; buttons disable while running).

- **Scraped fetch UI** (needs the host fetcher running: `scripts/fetcher.sh start` (also `stop|status|logs`); a badge shows up / not running): card detail -> "Fetch prices" (pick sources, `force` ignores the 24 h cache); per-source status line with last result, link, and a candidate picker when a match is ambiguous ("Use this" confirms and re-fetches that source, "Reset match" undoes it); Settings -> Prices -> "Price fetching" (selected sets, owned collection or missing prices, with progress and failure / needs-match lists); Search -> tick cards -> "Fetch prices for N selected". Scheduled runs never pause for login (see Scheduler). If a site needs a login a manual run pauses with "Waiting for login (<site>)": log in in the Chrome window that opened, the fetch continues.
- **Scraped fetch API**: `curl -X POST localhost:8100/api/admin/prices/fetch -H 'content-type: application/json' -d '{"cards":["pokemon:sv3pt5-205"],"sources":["altxyz"],"force":true}'`; targets: `cards`, `sets`, `owned`. Progress in `GET /api/admin/jobs` (`stats.waiting_login`, `needs_match_list`, `failures`). One card: `POST /api/cards/{id}/fetch-prices`.

## Usage

```bash
cp .env.example .env            # set MONGO_ROOT_PASSWORD
docker compose up -d --build    # mongo + api + web
```

| What | URL |
|---|---|
| Web | http://localhost:5180 |
| API + Swagger | http://localhost:8100/docs |

1. Settings -> Import: type a set id (e.g. `base1`) for a quick start, or leave empty for the full catalog (~20k cards, 30+ min, runs in the background; watch the Jobs tab).
2. Search -> open a card -> Add to collection.
3. Dashboard -> Refresh prices (re-fetches owned cards' sets, then takes today's snapshot). History needs 2+ snapshots to draw.

Data lives in docker volume `moc_mongo_data`. Never `docker compose down -v`. The backend has no auto-reload: `docker compose restart app` after edits.

### Price fetcher (host Mac, optional until Phase 3 lands)

Needs Google Chrome installed. One command: `scripts/fetcher.sh start` (check `curl localhost:8110/health`); nothing else is needed from you unless a Chrome window opens with a Cloudflare / login page: solve it there, the fetch continues. Chrome closes after 120 s idle. Setup (first time) and details: `fetcher/README.md` (`python3 -m venv .venv && pip install -e .[dev]`, then `python -m fetcher`). It only opens Chrome while a fetch runs.

Tests: see `CLAUDE.md` for the commands. Backend: pytest against a throwaway mongo. Frontend: `docker compose exec web npm test` (vitest + jsdom + Testing Library; `fetch` is mocked via `web/src/test/utils.tsx`, no network). UI failure handling: `QueryState`/`QueryError` (`web/src/components/QueryState.tsx`) show an error box with Retry when a query fails; `ErrorBoundary` catches render crashes; unknown URLs show a NotFound page.

## More

- `architecture.md` - technical design, data model, API
- `pricing.md` - price semantics, valuation rules, sources
- `decisions.md` - discovery answers and source findings
- `backup.md` - backup, verify, restore, scheduling
- `roadmap.md` - status, your pending tasks, open decision, backlog

## Demo data (UI checks without touching your collection)

```bash
docker compose run --rm app python -m app.scripts.demo_db create   # seeds owncollection_demo (needs Mew ex 151 #205 data in the real DB)
docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d app   # app on the demo DB
docker compose up -d app                                            # back to the real DB
docker compose run --rm app python -m app.scripts.demo_db drop     # delete the demo DB
```

## Look and theme
Dark by default. Header toggle: light / system / dark (remembered in the browser). UI building blocks live in `web/src/components/ui`.

## Export / import
Settings -> Data: JSON (lossless) or CSV (spreadsheet; money in cents). Import matches stacks by key, so re-importing the same file changes nothing ("set quantities") or adds quantities ("add"). API: `GET /api/collection/export?format=json|csv`, `POST /api/collection/import?format=&mode=set|add` (file as raw body).

## Backup
`scripts/backup.sh` dumps the whole database to `backups/`; `scripts/restore.sh` restores (or `--to-scratch` verifies). Scheduling, retention, restore steps: `docs/backup.md`.

## Alerts
Alerts page (nav badge = unread; two columns: Inbox left; "How alerts work" explainer, Rules table and the new-rule form right). The form reads as a sentence ("Alert me when [collection total | a card | a single stack] [searchable picker] [goes above | drops below | rises by | falls by] [amount] ...") with a live preview of the resulting rule; the picker searches all owned stacks server-side with "Show more" (no 200 cap). Rules can be disabled or deleted (delete asks to confirm). Add a rule on a stack, a card or the collection total (above/below a EUR amount, or up/down N% over D days; sold/market/any; optionally include estimated values). Rules are checked after every price fetch, refresh and snapshot ("Check now" re-checks). Each crossing gives one inbox item; the rule re-arms when the condition clears. A rule that is already true fires on the next check. The inbox also warns when a scheduled fetch was skipped (fetcher down / login needed).

## Scheduler
Off by default. Set `SCHEDULER_ENABLED=true` in `.env` and `docker compose restart app`. Daily catalog-API refresh, scraped fetch of owned cards (needs `scripts/fetcher.sh start`, else the run shows as `skipped`; sites needing login are skipped, so log in via a manual fetch now and then), snapshot, weekly catalog import, daily prune of old read alerts (`ALERT_EVENTS_KEEP_DAYS`, 90); missed runs are caught up at boot. Settings shows next runs and a trigger column in the Jobs table. Cron/cap settings: `docs/architecture.md`. Restart the host fetcher after updating (`scripts/fetcher.sh stop && scripts/fetcher.sh start`) so it knows the unattended flag.

### Card page prices (Phase 9.4e)
One grade selector (Raw | Any | PSA | BGS | CGC ... then grade 10 to 1) drives both the price matrix and the history chart and is kept in the URL (`?grade=PSA10`). The matrix shows only the chosen company's rows, hides empty grades/columns ("Show empty grades" reveals them) and highlights the selected row. "Any" has no grade 10 (PriceCharting publishes company-agnostic grades up to 9.5 only). Sold section: one stats table plus filterable sales (grade, source, 20 at a time, listing link). Chart: range 3m/6m/1y/all, ask series hidden unless ticked, one point shows a hint. Source status lives in a collapsed "Sources" section.

