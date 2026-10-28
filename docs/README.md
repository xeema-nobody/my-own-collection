# my-own-collection

Personal, local, single-user web app to administer trading-card collections. Pokémon TCG first; schema is generic (`tcg` field) so other TCGs plug in via a new catalog provider.

## Features

- **Catalog**: cards and sets imported from an external API into own MongoDB. Idempotent (re-import is safe).
- **Search**: free text over name / set / number / types / rarity / rules text (accent-insensitive, multi-token AND, `4/102`, `#4`, `base1-4`). Filters: set, type, rarity, supertype, price range, has price (yes/no), owned only. Unpriced cards sort last on price ascending. Sort by release, name, price. URL-synced filters.
- **Card detail**: image, metadata, prices per source, price history chart, sold-sales stats, owned stacks (+/−/remove), add-to-collection form.
- **Collection**: stacks of identical copies (card + variant + language + condition or grading). Raw copies need a condition; graded copies need grader + grade (optional cert, which makes the slab unique). Purchase price/date/notes. Browser with filters, sort, value, cost, P/L. Graded copies are valued at their own grade's price (sold median when >=3 sales in 90 d, else market); each value shows a `sold`/`market` badge and source, and `≈` with a reason when it is a fallback (grade bucket, lower grade, raw price) - see `pricing.md`.
- **Prices**: aggregate market prices from TCGplayer (USD) and Cardmarket (EUR), converted to the base currency (default EUR). Manual sale entry for sources without an API (e.g. alt.xyz).
- **Dashboard**: value KPIs (with count of estimated values), value-over-time line for the best value plus one per source (daily snapshots; change % compares only snapshots taken since graded valuation), breakdown by set / rarity / condition / language / TCG, top movers (sold-based, graded-aware; need the same kind of price now and N days ago), a reliability card (% of value that is sold-based), € labels on all charts. Hollow dots on the per-source lines = that source valued something thin or not exact.
- **Settings**: set picker (per-set priced/total) to import or refresh prices for chosen sets, "Retry failed imports" for sets that failed the last full import, provider status, job log. One job per type at a time (second start returns 409; buttons disable while running).

- **Scraped fetch UI** (needs the host fetcher running: `scripts/fetcher.sh start` (also `stop|status|logs`); a badge shows up / not running): card detail -> "Fetch prices" (pick sources, `force` ignores the 24 h cache); per-source status line with last result, link, and a candidate picker when a match is ambiguous ("Use this" confirms and re-fetches that source, "Reset match" undoes it); Settings -> "Fetch scraped prices" (selected sets or owned collection, with progress and failure / needs-match lists); Search -> tick cards -> "Fetch prices for N selected". Scheduled runs never pause for login (see Scheduler). If a site needs a login a manual run pauses with "Waiting for login (<site>)": log in in the Chrome window that opened, the fetch continues.
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

1. Settings -> Import: type a set id (e.g. `base1`) for a quick start, or leave empty for the full catalog (~20k cards, 30+ min, runs in the background; watch the Jobs table).
2. Search -> open a card -> Add to collection.
3. Dashboard -> Refresh prices (re-fetches owned cards' sets, then takes today's snapshot). History needs 2+ snapshots to draw.

Data lives in docker volume `moc_mongo_data`. Never `docker compose down -v`. The backend has no auto-reload: `docker compose restart app` after edits.

### Price fetcher (host Mac, optional until Phase 3 lands)

Needs Google Chrome installed. One command: `scripts/fetcher.sh start` (check `curl localhost:8110/health`); nothing else is needed from you unless a Chrome window opens with a Cloudflare / login page: solve it there, the fetch continues. Chrome closes after 120 s idle. Setup (first time) and details: `fetcher/README.md` (`python3 -m venv .venv && pip install -e .[dev]`, then `python -m fetcher`). It only opens Chrome while a fetch runs.

Tests: see `CLAUDE.md` for the command.

## More

- `architecture.md` - technical design, data model, API
- `pricing.md` - price semantics, valuation rules, sources
- `decisions.md` - discovery answers and source findings
- `roadmap.md` - future work (to be filled)

## Demo data (UI checks without touching your collection)

```bash
docker compose run --rm app python -m app.scripts.demo_db create   # seeds owncollection_demo (needs Mew ex 151 #205 data in the real DB)
docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d app   # app on the demo DB
docker compose up -d app                                            # back to the real DB
docker compose run --rm app python -m app.scripts.demo_db drop     # delete the demo DB
```

## Scheduler
Off by default. Set `SCHEDULER_ENABLED=true` in `.env` and `docker compose restart app`. Daily catalog-API refresh, scraped fetch of owned cards (needs `scripts/fetcher.sh start`, else the run shows as `skipped`; sites needing login are skipped, so log in via a manual fetch now and then), snapshot, weekly catalog import; missed runs are caught up at boot. Settings shows next runs and a trigger column in the Jobs table. Cron/cap settings: `docs/architecture.md`. Restart the host fetcher after updating (`scripts/fetcher.sh stop && scripts/fetcher.sh start`) so it knows the unattended flag.
