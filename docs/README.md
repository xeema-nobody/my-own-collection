# my-own-collection

Personal, local, single-user web app to administer trading-card collections. Pokémon TCG first; schema is generic (`tcg` field) so other TCGs plug in via a new catalog provider.

## Features

- **Catalog**: cards and sets imported from an external API into own MongoDB. Idempotent (re-import is safe).
- **Search**: free text over name / set / number / types / rarity / rules text (accent-insensitive, multi-token AND, `4/102`, `#4`, `base1-4`). Filters: set, type, rarity, supertype, price range, has price (yes/no), owned only. Unpriced cards sort last on price ascending. Sort by release, name, price. URL-synced filters.
- **Card detail**: image, metadata, prices per source, price history chart, sold-sales stats, owned stacks (+/−/remove), add-to-collection form.
- **Collection**: stacks of identical copies (card + variant + language + condition or grading). Raw copies need a condition; graded copies need grader + grade (optional cert, which makes the slab unique). Purchase price/date/notes. Browser with filters, sort, value, cost, P/L.
- **Prices**: aggregate market prices from TCGplayer (USD) and Cardmarket (EUR), converted to the base currency (default EUR). Manual sale entry for sources without an API (e.g. alt.xyz).
- **Dashboard**: value KPIs, value-over-time line per source (daily snapshots), breakdown by set / rarity / condition / language / TCG, top movers.
- **Settings**: set picker (per-set priced/total) to import or refresh prices for chosen sets, "Retry failed imports" for sets that failed the last full import, provider status, job log. One job per type at a time (second start returns 409; buttons disable while running).

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

Tests: see `CLAUDE.md` for the command.

## More

- `architecture.md` - technical design, data model, API
- `pricing.md` - price semantics, valuation rules, sources
- `decisions.md` - discovery answers and source findings
- `roadmap.md` - future work (to be filled)
