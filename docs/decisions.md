# Decisions (discovery, Phase A)

Answered by user: Q6/Q7 EUR base, EN+JA; Q12 full catalog in background (dev: base1 + sv3pt5); Q20 commit per phase on a feature branch, local only, no push.
Local-only run: docker compose, mongo with named volume `moc_mongo_data` (survives `down`; never use `down -v`).

Asked by user, answered:
- Q1 PriceCharting: **superseded** (see Scraping decisions). No API token, no paid plan. Data via browser fetcher.
- Q2 alt.xyz: **superseded**. Fetched by the browser fetcher (sold list works anonymously); manual sale entry (`POST /api/cards/{id}/sales`) stays as source `manual`.
- Q4: aggregate = provider-computed market number; sold = individual completed sales. Both stored with `kind`; sold stats (last 10 / 90d) shown when sales exist, aggregate badged otherwise. User wants statistics from trustworthy data -> prefer sold when available.

## Scraping decisions (user, 2026-10-27)
1. Sold-price scraping: YES. Sources PriceCharting, Cardmarket, alt.xyz (+ pokemontcg.io aggregate as optional 4th). Shown in card detail, collection, dashboard.
2. No PriceCharting token. Catalog stays pokemontcg.io (no Scrydex).
3. Sold = real value (D-A). Roadmap: graded pricing -> scheduler -> alerts.
4. Fetch only when the user asks (card button; Settings: set / owned / one card). Each site is tried without login first; if login or a challenge is needed a visible tab opens on that site, the fetch waits ("waiting for login (<site>)"), the user logs in themselves, fetch continues. We never see or store credentials. Sessions persist in a dedicated Chrome profile.
5. Fetcher runs on the host Mac (not Docker); the app calls it over localhost HTTP. Browser closes after idle.

Defaulted by me (change on objection):
- **D-A** value per copy = sold-based price if >=3 sold sales in last 90d for that card+grade (median of last 10); else source market/trend aggregate; else unpriced. Each price has `kind` (`sold|market|ask`), UI badges it, never mixed silently. Median, not mean. `manual` highest trust.
- **D-B** one host-Mac fetcher driving **real Google Chrome over CDP** (`--remote-debugging-port`, dedicated `--user-data-dir`), Playwright `connect_over_cdp`. Playwright's bundled Chromium (headless or headed) is blocked by Cloudflare on Cardmarket; real Chrome passes. PriceCharting and alt.xyz also work headless, but one engine is simpler.
- **D-C** on demand only, polite: 1 request / 3-5 s per site, concurrency 1 per site, cache 24h, no bulk catalog crawl.
- **D-D** one observation per (card, variant, source, kind, grade_key, fetch date); upstream `as_of` kept as field.
- **D-E** store native currency, convert to base at read via FX.

Defaults taken (assumptions): Q3 cardmarket aggregates from catalog payload; Q5 keyless pokemontcg.io (works, flaky: retries on 5xx); Q8 graders PSA/BGS/CGC/SGC/ACE/OTHER; Q9 stacks (slabs w/ cert unique); Q10 P/L on; Q11 from scratch; Q13 collection daily + catalog on demand; Q14 scheduler off; Q15 local, no auth, bind 127.0.0.1; Q16 Vite SPA, dark+light, English; Q17 api 8100, web 5180, prefix `moc-`; Q18 Pokemon only; Q19 backup service deferred to Phase 7.

## Data source findings (2026-10-27)
- pokemontcg.io is **deprecated**: new keys closed, existing keys valid until 2027-03-01; keyless works but returns intermittent 500/502 (retried with backoff).
- Successor Scrydex: paid, from $29/mo (5k credits), includes raw+graded prices. Not adopted; swap in via `CatalogProvider`.
- Frankfurter moved to `api.frankfurter.dev/v1`.
- Cardmarket `updatedAt` in the payload can be months old: shown as `as_of`.
- Product matches live in their own collection `product_matches`, not `cards.external_ids`: catalog import rewrites `external_ids.cardmarket_url` (aggregate link) on every run. User-confirmed matches take precedence over auto ones.

## Phase 4: graded valuation (2026-10-28, defaults by me, change on objection)
- Ask prices are never used for valuation.
- A company-agnostic bucket match (`G9` for a PSA 9) is NOT exact: shown with `≈` and a reason.
- Sold rule (>=3 in 90 d, median of last 10), `PREFERRED_SOURCES` order are settings in `app/config.py`; no Settings UI. Sold sales are pooled across sources.
- Scraped raw sales never value raw items (condition unknown); manual ones do.
