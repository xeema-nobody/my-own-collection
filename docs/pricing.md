# Pricing

## Sources

| Source | How | Kind | Notes |
|---|---|---|---|
| TCGplayer | embedded in pokemontcg.io payload | market (aggregate), USD, per variant | low / mid / high / market |
| Cardmarket | embedded in pokemontcg.io payload | market (aggregate), EUR, `variant=None` | low / avg / trend / avg7 / avg30; uses trend as `market`; `as_of` can be stale |
| Manual / alt.xyz | `POST /api/cards/{id}/sales` | sold | user-entered comps |
| PriceCharting | paid API token | market | provider disabled; not implemented |

Aggregate = provider-computed number; sold = individual completed sale. UI labels aggregate prices "Market price (aggregate)" and shows sold min/avg/max when sales exist.

## Data model v2 (observation log)

`prices` row = one observation: `{card_id, variant|None, source, kind: sold|market|ask, grade_key ('raw'|'PSA9'|...), currency, observed_on, as_of, low, avg, median, high, market, sample_size, url, fetched_at}`.
Unique key `(card_id, variant, source, kind, grade_key, observed_on)`; `observed_on` = UTC date of *our* fetch, `as_of` = upstream timestamp (nullable, may be stale). Same-day re-fetch overwrites; a new day adds a point. Upstream 0 = no data -> `None`.
`cards.latest_price[source][kind][grade_slot][variant_slot]` holds the newest value (`variant_slot` `_` = no variant; `grade_slot` replaces `.` with `_`). `cards.price_base` = headline raw price (cardmarket, else tcgplayer). `cards.price_schema = 2`.
`variants` is `[]` when the card has no real variants; `CollectionIn.variant` is optional (None). Migration `app/db/migrate_prices_v2.py` runs idempotently on boot. Source registry: `app/providers/price/__init__.py` (`GET /api/admin/price-sources`).

## Valuation

- Item value = quantity x source market price, converted to base currency (FX from frankfurter.dev, cached daily).
- tcgplayer: matching variant, else first variant (flagged estimated). cardmarket: single price for any variant.
- Graded items have no graded prices yet: valued at raw price, flagged estimated (`≈`).
- Headline value = cardmarket if present, else tcgplayer. Unpriced items counted, not valued at 0.
- Cost = acquired price converted at today's rate. P/L = value - cost (null when no cost recorded).

## Snapshots

Taken after each refresh (or `POST /api/admin/snapshot`). One per UTC date. No backfill possible: history starts at the first snapshot.

## Unpriced cards
Some sets/cards have no price block in the pokemontcg.io payload (e.g. `me55`, `me5`, `me2pt5`, `mcd*`, `tk*`), so they stay unpriced (`price_base = None`, shown as "no price"). That is a source gap, not an import failure; only another source can fill it. Settings shows priced/total per set.
