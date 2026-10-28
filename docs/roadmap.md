# Roadmap

Done: catalog + collection (0-1), price model v2 (2), scraped fetch + sold sales (3), graded valuation (4).

Next (order, see `temp/follow_up.md` for detail):
5. Dashboard review with multi-day data (value by source/kind, sold-based movers, empty states). Open point: movers still use raw cardmarket; `cardmarket_web` raw can differ a lot from `cardmarket`, check `PREFERRED_SOURCES` order.
6. Scheduler + boot catch-up (daily fetch of owned items, snapshot, weekly catalog import).
7. Price alerts.
8. Hardening: export/import, mongo backup, perf, reviews.
