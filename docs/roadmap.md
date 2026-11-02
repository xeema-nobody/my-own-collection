# Roadmap

## Done (phases 0-8)
Catalog + collection (0-1), price model v2 (2), scraped fetch + sold sales (3), graded valuation (4), dashboard (5), compare sources (5b), scheduler + catch-up (6), price alerts (7), hardening (8: export/import, mongo backup, perf, FE error states + tests, backend gap tests, security review, alert prune, alt.xyz paging, unread label).

## Pending operator tasks (yours, not code)
Do in this order; the app works without them but runs manual-only until they are done.

1. **Restart the host fetcher after every pull** so it picks up new fetcher code (`pages`/`next_label` one-navigation alt.xyz paging, `unattended` flag): `scripts/fetcher.sh stop && scripts/fetcher.sh start`. The fetcher is a separate process, `docker compose restart app` does not touch it. Stale fetcher symptom: alt.xyz returns only the first page of sales (old fetcher ignores `pages`). If `scripts/fetcher.sh stop` says "no pidfile" but `status` is up, kill the process on :8110 by hand.
2. **Install the backup schedule** (`backup.md`, section "Schedule"): one cron line or launchd plist on the host, daily 05:30. Then run `scripts/restore.sh backups/<file> --to-scratch` once to prove a dump restores. The docker volume is the only copy of your data until this exists.
3. **Run the scheduler for a few days**: `SCHEDULER_ENABLED=true` in `.env`, `docker compose restart app`, keep `scripts/fetcher.sh` running and the Mac awake around 03:00-06:30 UTC (missed runs catch up at boot). Watch Settings -> Jobs (trigger column) and the Alerts inbox for `skipped` warnings. Sites that need a login are skipped unattended: do a manual fetch now and then to refresh the session. Purpose: shake out real-world failures before trusting it.

## Decided: `ALTXYZ_MAX_PAGES` (2026-11-02)
Closed by one-navigation paging: the fetcher loads the alt.xyz list once and clicks "Go to next page" in the same tab, returning one snapshot per page. Live check (Mew ex 205, 3 pages): 19 s, 30 distinct listings, was ~66 s. Default stays 3; no per-trigger cap needed. Raise it only if a card's useful sales still sit past page 3 (the 180 d recency stop usually ends paging first).

## Phase 9: fix and polish what exists (priority, before the backlog)
Triggered by first real use (2026-10-29). Detail and root causes: `temp/follow_up.md`.
1. **DONE (9.1)** Catalog completeness: Unified Minds (`sm11`) had 100 of 260 cards, pokemontcg.io fails on page 2+. Adaptive paging, per-set completeness, retry incomplete.
2. **DONE (9.2)** Valuation correctness: a graded stack with no graded price is not counted (today it falls back to the raw price and inflates the total, 8 of 15 stacks); fetch prices automatically when a card is added.
3. **DONE (9.3)** Design foundation: CSS-variable tokens (neutral + emerald), Inter (@fontsource), light/dark/system toggle, wide sticky shell, `web/src/components/ui/` kit (Button, Card/Section, Badge, Field/Input/Checkbox, Select, Tabs/SegmentedControl, Kpi, Skeleton/EmptyState; radix + lucide). Default theme dark. Search + Card page shell restyled as preview.
4. Screens, in this order (user decision 2026-10-29): Collection (pagination, sort, filters, value chart; DONE 2026-10-29), Dashboard (insights vs inventory; DONE 2026-10-29), Alerts (explained, guided form; DONE 2026-10-29), Settings (tabs, set browser, readable jobs; DONE 2026-10-29), then PriceMatrix + price chart on card detail (DONE 2026-10-29); Card page Owned + Add panels (DONE 2026-10-30), Search polish (DONE 2026-10-29: Combobox set filter, filter chips + clear all, sort Select, selection bar, set symbol/header). **Phase 9 complete 2026-10-31** (legacy classes removed, final screenshots in `docs/screenshots/`).

## Backlog (after Phase 9, in order)
a. **DONE 2026-10-31 (branch feat/wishlist)** **Wishlist**: cards you want but do not own. Target price, optional alert when the price falls below it (reuse the alert engine), shown in a Wishlist page and as a flag on search/card detail. Needs: `wishlist` collection, API, page, alert scope.
b. **DONE 2026-11-02 (branch feat/toolchain-bump: vite 8, vitest 4, react-router-dom 7, npm audit = 0)** **Toolchain bump** for the 8 `npm audit` findings (vitest 4, vite 8, react-router 7). All fixes are semver-major. Findings are dev-only except react-router, whose advisories do not apply here (see `decisions.md`, Phase 8 review). Do it as one branch, re-run `npm audit`, typecheck and `npm test`. Low urgency while nothing is deployed.
c. **One-navigation multi-page fetch** for alt.xyz: the fetcher clicks through pages inside a single page load and returns every page's HTML in one response, instead of one navigation per page. Removes most of the cost in the open decision above, makes 3+ pages cheap, and then the cap question goes away. Needs a fetcher response shape change (list of HTML snapshots) and adapter update.

## Later / ideas (unscheduled)
- Notification outside the UI (host fetcher polls `/api/alerts/events?unread=true` and shows a macOS notification).
- Replace pokemontcg.io (deprecated, keys valid until 2027-03-01) with another `CatalogProvider`, e.g. Scrydex (paid) or a static dataset.
- Other TCGs via new catalog providers (schema is already generic).
- Auth, non-root containers, rate limiting, prod image: only if the app is ever deployed beyond localhost.
