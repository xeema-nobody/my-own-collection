# CLAUDE.md

Guidance for Claude Code in this repo. Keep current when tooling or layout changes.

## What this is

**my-own-collection** — personal TCG collection manager (Pokémon first, schema generic). FastAPI + Motor (MongoDB 7) backend, Vite React TS SPA. Local only, single user, no auth. Docs: `docs/README.md` (overview/usage), `architecture.md`, `pricing.md`, `decisions.md`, `roadmap.md`. Session context: `temp/follow_up.md` (gitignored).

## Layout

```
app/                 Python backend
  main.py            FastAPI app, lifespan (indexes, scheduler), CORS, /health, /health/ready
  config.py          pydantic-settings (.env)
  db/                mongo.py (client, init_indexes), models.py (request models)
  api/               routers per domain: cards, collection, dashboard, alerts, admin
  services/          catalog_import, search, collection (valuation), pricing, fx, snapshots, alerts, refresh, jobs
  providers/         catalog/ (CatalogProvider, pokemontcg), price/ (fx)
  jobs/scheduler.py  APScheduler, only if SCHEDULER_ENABLED
web/                 Vite React SPA (src/pages, src/lib/api.ts = single API client)
tests/  docs/
```

## Commands

```bash
docker compose up -d --build          # mongo + api :8100 + web :5180 (vite dev)
docker compose restart app            # backend has no --reload; restart after edits
docker compose run --rm -v $PWD/tests:/code/tests -v $PWD/pytest.ini:/code/pytest.ini app sh -c "pip install -q pytest pytest-asyncio && python -m pytest"
docker compose exec web npx tsc --noEmit   # FE typecheck
docker compose exec web npm test         # FE vitest (jsdom, fetch mocked)
scripts/backup.sh                     # mongodump -> backups/ (docs/backup.md)
scripts/restore.sh <file> [--to-scratch]   # restore / verify a dump
```
Never `docker compose down -v` (deletes the mongo volume = all collection data).

## Conventions

- Layered: routers thin -> `services/` -> `providers/` + `db/`. Only providers call httpx.
- Money = integer cents + currency, never floats. Missing price = `None`, never 0.
- Idempotent writes (upsert on natural key); re-running import/refresh/snapshot is safe.
- Config via `app/config.py`; FE calls only via `web/src/lib/api.ts`.
- Long jobs run as asyncio tasks, state in `jobs` collection.
- No live network in tests; fixtures under `tests/fixtures/`.

## Don't touch

`.env` (secrets; never read/print/commit), `temp/`, generated dirs.

## Claude setup

`.claude/settings.json` enables caveman + trailofbits plugins; `.claude/skills` copied from make-me-rich (testing, security, review audits); `/feature` command.
