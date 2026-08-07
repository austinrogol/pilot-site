# pilot-site

Agent Economy supervised publication pilot.

`index.html` is the pilot's published static page and is unrelated to the
Python service described below.

---

# edgeloop II

Quantitative security research and portfolio risk, with a forecast ledger that
scores itself against reality over time.

Read **[`docs/NON_NEGOTIABLES.md`](docs/NON_NEGOTIABLES.md)** before changing
anything in `quant/` or `ledger/`. Read
**[`docs/PHASE1_REPORT.md`](docs/PHASE1_REPORT.md)** for what is verified, what
is guessed, and what is missing.

## Status

| Phase | Scope | State |
|---|---|---|
| 1 | FMP client, caching, rate governor, schema, migrations | **complete** — 89 tests green |
| 2 | Quant core + spec tests 1–4 | not started |
| 3 | Ledger write/resolve + scheduled job (test 5) | schema + constraint done; write path not started |
| 4 | Portfolio module, real covariance (test 6) | not started |
| 5 | FastAPI routes, frontend | not started |

**Nothing forecasts yet.** The ledger is empty, and that is correct — see
non-negotiable 4.

## Quickstart

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head
.venv/bin/python -m edgeloop.scripts.prove_ticker NVDA   # recorded bodies, no key needed
.venv/bin/python -m pytest
```

With a key (`FMP_API_KEY` in the environment — **never in the repo**):

```bash
.venv/bin/python -m edgeloop.scripts.prove_ticker NVDA --live
```

The live run is also the fastest way to find out which inferred endpoint paths
are wrong; see `docs/PHASE1_REPORT.md` §2.

## Layout

```
edgeloop/
  config.py          # settings; drift shrinkage priors live here, not in a function
  data/
    endpoints.py     # endpoint registry -- every guessed path is marked as guessed
    fmp.py           # async client: cache -> governor -> transport -> parse -> provenance
    transport.py     # the only object that sees FMP_API_KEY
    cache.py         # disk cache keyed (endpoint, params, date)
    governor.py      # trailing-24h call budget, fails closed
    schemas.py       # typed responses, written against real bodies
    provenance.py    # source, fetched_at, data_asof, quality, missing[]
    models.py        # SQLAlchemy schema; no-lookahead is a DB CHECK
    db.py            # engine/session; DATABASE_URL switches SQLite <-> Postgres
  quant/             # phase 2
  ledger/            # phase 3
  api/               # phase 5
fixtures/            # real FMP bodies for NVDA, captured 2026-08-07
migrations/          # alembic; env.py owns the URL, alembic.ini does not
tests/
```

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `FMP_API_KEY` | unset | Secrets in env only. Never in the repo, logs, or a response body. |
| `DATABASE_URL` | local SQLite | The single switch to Postgres (Railway). |
| `FMP_MAX_CALLS_PER_DAY` | 240 | Self-imposed cap under the free tier's few-hundred/day. |
| `EDGELOOP_SHRINK_1Y` | 0.78 | Shrinkage toward CAPM at 1y. A tunable prior, not a constant. |
| `EDGELOOP_SHRINK_3Y` | 0.60 | Same at 3y+. |

A single ticker analysis costs **7 uncached calls**, against a budget of 8.

## What this system will not do

No order execution. No brokerage write access. Read-only and advisory, full
stop. No options-implied anything (FMP sells no options data at any tier). No
news sentiment scoring. See `docs/NON_NEGOTIABLES.md`.
