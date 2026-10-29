# Roadmap

## Done (phases 0-8)
Catalog + collection (0-1), price model v2 (2), scraped fetch + sold sales (3), graded valuation (4), dashboard (5), compare sources (5b), scheduler + catch-up (6), price alerts (7), hardening (8: export/import, mongo backup, perf, FE error states + tests, backend gap tests, security review, alert prune, alt.xyz paging, unread label).

## Pending operator tasks (yours, not code)
Do in this order; the app works without them but runs manual-only until they are done.

1. **Restart the host fetcher after every pull** so it picks up new fetcher code (`click_labels` for alt.xyz paging, `unattended` flag): `scripts/fetcher.sh stop && scripts/fetcher.sh start`. The fetcher is a separate process, `docker compose restart app` does not touch it. Stale fetcher symptom: alt.xyz returns only the first page of sales.
2. **Install the backup schedule** (`backup.md`, section "Schedule"): one cron line or launchd plist on the host, daily 05:30. Then run `scripts/restore.sh backups/<file> --to-scratch` once to prove a dump restores. The docker volume is the only copy of your data until this exists.
3. **Run the scheduler for a few days**: `SCHEDULER_ENABLED=true` in `.env`, `docker compose restart app`, keep `scripts/fetcher.sh` running and the Mac awake around 03:00-06:30 UTC (missed runs catch up at boot). Watch Settings -> Jobs (trigger column) and the Alerts inbox for `skipped` warnings. Sites that need a login are skipped unattended: do a manual fetch now and then to refresh the session. Purpose: shake out real-world failures before trusting it.

## Open decision: `ALTXYZ_MAX_PAGES`
alt.xyz paging costs one browser navigation per page, so it takes ~66 s per card at the default of 3 pages (was ~15 s with 1). Scheduled fetch caps at 300 cards/run, so worst case is hours, plus the 3-5 s politeness delay per site.

| Option | Cost per card | Effect |
|---|---|---|
| 3 pages (default) | ~66 s | up to ~28 sales per card, best median |
| 2 pages | ~40 s | about two thirds of the sales; still enough for the >=3-in-90-days rule on most cards |
| 1 page | ~15 s | original behaviour, ~10 sales |

Recommendation: decide **before** enabling the scheduler. Cap at 2 for scheduled runs if the nightly run is too long (watch the first run's duration), keep 3 for manual single-card fetches. Today it is one global setting (`altxyz_max_pages`), so a per-trigger cap would be a small code change. The real fix is backlog item c.

## Phase 9: fix and polish what exists (priority, before the backlog)
Triggered by first real use (2026-10-29). Detail and root causes: `temp/follow_up.md`.
1. **DONE (9.1)** Catalog completeness: Unified Minds (`sm11`) had 100 of 260 cards, pokemontcg.io fails on page 2+. Adaptive paging, per-set completeness, retry incomplete.
2. **DONE (9.2)** Valuation correctness: a graded stack with no graded price is not counted (today it falls back to the raw price and inflates the total, 8 of 15 stacks); fetch prices automatically when a card is added.
3. Design foundation: palette, fonts, light/dark toggle, wider layout, shared UI components.
4. Screens: card detail, collection (pagination, sort, filters, value chart), dashboard (clear purpose: insights vs collection inventory), settings (set browser, readable jobs), alerts (explained, guided form), search.

## Backlog (after Phase 9, in order)
a. **Wishlist**: cards you want but do not own. Target price, optional alert when the price falls below it (reuse the alert engine), shown in a Wishlist page and as a flag on search/card detail. Needs: `wishlist` collection, API, page, alert scope.
b. **Toolchain bump** for the 8 `npm audit` findings (vitest 4, vite 8, react-router 7). All fixes are semver-major. Findings are dev-only except react-router, whose advisories do not apply here (see `decisions.md`, Phase 8 review). Do it as one branch, re-run `npm audit`, typecheck and `npm test`. Low urgency while nothing is deployed.
c. **One-navigation multi-page fetch** for alt.xyz: the fetcher clicks through pages inside a single page load and returns every page's HTML in one response, instead of one navigation per page. Removes most of the cost in the open decision above, makes 3+ pages cheap, and then the cap question goes away. Needs a fetcher response shape change (list of HTML snapshots) and adapter update.

## Later / ideas (unscheduled)
- Notification outside the UI (host fetcher polls `/api/alerts/events?unread=true` and shows a macOS notification).
- Replace pokemontcg.io (deprecated, keys valid until 2027-03-01) with another `CatalogProvider`, e.g. Scrydex (paid) or a static dataset.
- Other TCGs via new catalog providers (schema is already generic).
- Auth, non-root containers, rate limiting, prod image: only if the app is ever deployed beyond localhost.
