# Recorded FMP response bodies

Real responses for **NVDA**, captured from this account on **2026-08-07**.

## Why these exist

The phase 1 sandbox had no outbound route to `financialmodelingprep.com` (the
egress proxy refuses CONNECT for both the API host and the docs host) and no
`FMP_API_KEY`. These bodies were captured through FMP's own MCP server, which is
a different transport onto the same account and the same backing data.

That makes them the real thing in the way that matters -- field names, spellings,
types, null patterns, timestamp semantics -- which is what `schemas.py` is
written against. What they do **not** establish is that the REST paths in
`endpoints.py` are spelled correctly; only a live HTTP call can do that. See
`docs/PHASE1_REPORT.md`.

## Contents

| File | Registry key | Rows | Notes |
|---|---|---|---|
| `quote.json` | `quote` | 1 | `timestamp` is unix seconds |
| `historical-price-eod-light.json` | `historical_price_light` | 256 | 2025-08-01..2026-08-07. Close is `price`. Newest first. |
| `historical-price-eod-full.json` | `historical_price_full` | 4 | OHLC + vwap |
| `profile.json` | `profile` | 1 | `beta`, `averageVolume`. **`description` truncated** -- the only edit made to any body. |
| `stock-peers.json` | `peers` | 9 | market cap is `mktCap` here, `marketCap` in quote |
| `key-metrics-ttm.json` | `key_metrics_ttm` | 1 | every field suffixed `TTM` |
| `income-statement.json` | `income_statement` | 1 | `date` 2026-01-25 vs `acceptedDate` 2026-02-25 -- the point-in-time gap, one month wide |
| `price-target-consensus.json` | `price_target_consensus` | 1 | recorded, never an input to mu |
| `treasury-rates.json` | `treasury_rates` | 5 | quoted in percent |
| `market-risk-premium.json` | `market_risk_premium` | 6 | **trimmed from ~200 countries** to keep the file readable; the live endpoint returns every country and ignores its filter |

Two files are edited relative to what the API returned, both noted above and
nowhere else: the profile description and the risk-premium country list. No
numeric value in any fixture has been altered.
