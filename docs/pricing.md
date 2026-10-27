# Pricing

## Sources

| Source | How | Kind | Notes |
|---|---|---|---|
| TCGplayer | embedded in pokemontcg.io payload | market (aggregate), USD, per variant | low / mid / high / market |
| Cardmarket | embedded in pokemontcg.io payload | market (aggregate), EUR, single `default` variant | low / avg / trend / avg7 / avg30; uses trend as `market`; `as_of` can be stale |
| Manual / alt.xyz | `POST /api/cards/{id}/sales` | sold | user-entered comps |
| PriceCharting | paid API token | market | provider disabled; not implemented |

Aggregate = provider-computed number; sold = individual completed sale. UI labels aggregate prices "Market price (aggregate)" and shows sold min/avg/max when sales exist.

## Valuation

- Item value = quantity x source market price, converted to base currency (FX from frankfurter.dev, cached daily).
- tcgplayer: matching variant, else first variant (flagged estimated). cardmarket: single price for any variant.
- Graded items have no graded prices yet: valued at raw price, flagged estimated (`≈`).
- Headline value = cardmarket if present, else tcgplayer. Unpriced items counted, not valued at 0.
- Cost = acquired price converted at today's rate. P/L = value - cost (null when no cost recorded).

## Snapshots

Taken after each refresh (or `POST /api/admin/snapshot`). One per UTC date. No backfill possible: history starts at the first snapshot.
