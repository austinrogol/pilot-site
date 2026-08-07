# Phase 1 report

*Data layer: FMP client, caching, rate governor, schema, migrations.*
Built 2026-08-07 on branch `claude/edgeloop-ii-build-spec-mvgmkf`.

Phase 1 is complete and green. This document is the other half of the
deliverable: **what I had to guess at, and what I could not verify.**

---

## 1. Two of the three inputs the spec assumes do not exist

The spec opens by telling me to read prior work before writing anything. I
looked in this repo, in git history, and across every repository on the
account. Here is what is actually there.

### `edgeloop2.jsx` — NOT FOUND

The React prototype does not exist in `austinrogol/pilot-site` (which contained
only `README.md` and an unrelated `index.html`), is not in any deleted commit,
and is not in any other repository on the account. There is no `.jsx` file
anywhere.

**Consequence:** I ported the quant core from the spec's prose rather than from
the prototype. Where the spec describes a behaviour precisely — Student-t
quantiles, cumulative variance over h days, the shrinkage weights, `f* =
mu_excess / sigma^2` — that is enough. Where it says "port these from the
prototype, then improve them", I have only the "improve" half of the
instruction and no baseline to diff against.

**What I need from you:** the file, or confirmation to build phase 2 from the
spec text alone.

### `edgeloop` v1 — NOT FOUND (and the similarly-named repo is a different system)

`austinrogol/edge-loop` exists and is titled **"EdgeLoop 2.0 — Robinhood-native
quantitative portfolio intelligence and governance research system"**. It is a
TypeScript/Next.js/Cloudflare Workers project. I read it in full.

It is **not** the v1 the spec refers to:

- No GARCH, no Student-t, no quantiles, no Kelly sizing, no PIT.
- `runtime/math.mjs` has covariance/shrinkage/Sharpe utilities, but nothing
  resembling the four sizing constraints.
- `runtime/governor.mjs` enforces a genuinely different constraint set —
  capital ceiling, drawdown breaker, concentration, cash reserve — aimed at
  blocking *order intents*, not at sizing a position.
- I grepped both repos for `thesis.?break`, `volatility budget`, `exit
  capacity`, `single.?name cap`, `loss budget`, `snapshot`, `garch`, `kelly`,
  `crps`, `pit`. **Zero matches for any of the sizing-constraint terms.**

**Consequence:** the instruction "preserve its snapshot JSON contract and its
four sizing constraints … do not redesign them" **cannot be followed as
written**, because there is nothing to preserve. The four constraints are named
clearly enough in the spec that I can implement a defensible version, but
whatever I write will be a *redesign* by definition, and the snapshot JSON
contract I have no information about at all.

This binds in **phase 4** (`quant/sizing.py`, `quant/portfolio.py`), not
phase 1 — which is why I have carried on rather than stopping.

**What I need from you, before phase 4:** the v1 source, or the snapshot JSON
shape and the exact definition of each of the four constraints.

### `desk-trading` — FOUND, and used

`austinrogol/desk-trading` is real and relevant. The spec says "add a rate
governor like the one in desk-trading", and I ported
`research/llm_experiment/rate_governor.py` directly: trailing 24-hour window
rather than a calendar day, fail-closed on unreadable state, durable
atomically-written JSON. Its three design comments are carried across verbatim
in spirit and credited in `data/governor.py`.

One deliberate change: desk-trading caps *generation cycles* with a
minimum spacing in hours, where I cap *HTTP calls* with a spacing in seconds. I
split the decision into a **hard block** (daily cap spent, unreadable state,
future-dated entries) and a **soft block** (sub-second spacing), because a
spacing rule that *refuses* rather than *delays* turns a politeness throttle
into a budget. That distinction is in `Decision.hard_block` and is tested.

---

## 2. FMP endpoint paths are unverified — the sandbox has no route to FMP

The spec says: *"Verify every endpoint path against FMP's live docs before
coding — they have both `/api/v3` and `/stable` routes and I am not going to
guess which your key uses."*

**I could not do this, and you should know exactly why before trusting any URL
in `data/endpoints.py`.**

- `FMP_API_KEY` is **not set** in this environment.
- The egress proxy **refuses CONNECT** to both `financialmodelingprep.com` and
  `site.financialmodelingprep.com` (HTTP 403 on the tunnel). That blocks the
  API *and* the documentation site, via `curl` and via the fetch tool alike.

### What I did instead

FMP's own **MCP server** is available in this session — a different transport
onto the same account and the same backing data. I used it to establish two
things that matter:

**Plan entitlements, confirmed live.** The account is on the **free tier**.
`technicalIndicators` returned an explicit *"requires the Starter, Premium,
Ultimate, or Enterprise plan"* refusal, and the server's own metadata marks
`form13F`, `earningsTranscript`, `ESG`, `commitmentOfTraders` and `tipranks` as
Ultimate/Premium/add-on. **This matches your "confirmed blocked" list exactly.**
These are recorded in the registry as `PlanGate.BLOCKED` and kept visible rather
than deleted.

**Response shapes, confirmed live.** I pulled real bodies for ten endpoints and
wrote `data/schemas.py` against them. They are checked in under `fixtures/`.

### What remains unverified

Response *shape* verification says nothing about whether the REST *path* is
spelled right. Every endpoint therefore carries two independent status flags,
and the registry can report on itself:

```
18 endpoint paths  : PathStatus.INFERRED  -- derived from the MCP slug, never called
 2 endpoint paths  : PathStatus.DOCS      -- exact string found in FMP docs
                                             (historical-price-eod/light and /full)
10 response shapes : ShapeStatus.UNKNOWN  -- models are provisional
```

`python -m edgeloop.scripts.prove_ticker` prints both lists on every run.

**The first thing to do when you have a key:** run `--live` and fix whatever
404s. The client raises a targeted error on 404 that names the registry status
and explicitly refuses to fall back to `/api/v3`, because the v3 response field
names differ and a silent fallback would corrupt the schemas.

**Highest-risk path:** `ratios_ttm`. FMP's documentation *page* is slugged
`metrics-ratios-ttm` while the REST path is believed to be `ratios-ttm`. I could
not resolve this. It is flagged inline in the registry.

---

## 3. Things the API does that the spec doesn't mention

Found by reading real responses. Each is handled and annotated in code.

**`market-risk-premium` ignores its country filter.** Passing
`country="United States"` returns **all ~200 countries**. The client filters
client-side and records the fact in the provenance note, so the filtering isn't
invisible. It also carries **no date field at all** — we know when we fetched
it but not when it was last revised, so `data_asof` is `None` and that lands in
`missing[]`.

**FMP's field naming is not internally consistent.** The light price chart calls
the close `price`, not `close`. `quote` says `marketCap`; `stock-peers` says
`mktCap`. Both spellings are preserved in the models rather than normalised, so
that a response body and a model can be read side by side.

**`profile` and `key-metrics-ttm` publish no timestamp.** Every run produces
three `missing[]` entries for exactly this reason. That is the system working:
`data_asof` is `NULL` and explicitly *not* defaulted to the fetch time.

**Daily bars have a coarse `data_asof`.** FMP publishes EOD rows as a bare date
with no exchange timezone. I stamp them end-of-UTC-day rather than invent
16:00 America/New_York, then clamp to the fetch time when that reads as "after"
an intraday fetch. Both the convention and the clamp are noted in provenance.
This is the least satisfying compromise in the phase and I would revisit it if
intraday precision ever matters.

**`acceptedDate` has no timezone.** FMP returns `"2026-02-25 16:42:19"`. It is
SEC EDGAR acceptance, which is US Eastern, but I treat it as UTC — coarse by a
few hours, documented in `schemas.py`, not hidden. It does not affect a daily
forecast.

---

## 4. Other deviations from the spec, and why

**Python 3.11, not 3.12+.** The environment has 3.11.15, so PEP 695 generics
(`class Fetched[T]`) are a syntax error. Used `Generic[T]` instead. `requirements.txt`
says 3.11+ accordingly.

**Resolved dependency versions** (for reproducibility): fastapi 0.141.1,
httpx 0.28.1, pydantic 2.13.4, SQLAlchemy 2.0.51, alembic 1.19.0, numpy 2.4.6,
scipy 1.17.1, pandas 3.0.5, **arch 8.0.0**, pytest 9.1.1.

**The frontend cannot be repointed.** Build step 5 says "repoint the React
prototype at these routes". There is no prototype (see §1). Phase 5 will need
either the file or a decision to write a new frontend.

**`alembic.ini` carries no URL.** `migrations/env.py` reads `DATABASE_URL`
through `edgeloop.config` instead, so there is one source of truth rather than
two that eventually disagree. `render_as_batch` is on because SQLite cannot
`ALTER` a constraint — without it, a future migration touching the no-lookahead
CHECK would silently no-op.

---

## 5. Two bugs found and fixed while building

Recorded because both were real defects in my own first cut, not hypotheticals.

**The rate governor refused calls it should have delayed.** The first
end-to-end run stopped on call two: the 0.25s minimum spacing was treated as a
hard refusal, and the fixture transport is instantaneous. Fixed by splitting
`Decision` into hard and soft blocks (§1). A budget should refuse; a throttle
should wait.

**SQLite foreign keys were enforced only if you used the right constructor.**
`create_db_engine` attached the `PRAGMA foreign_keys=ON` listener to one engine
instance, so a test — or a script, or a migration — calling `create_engine`
directly silently lost referential integrity. A test caught this by doing
exactly that. The listener is now registered against the `Engine` class, so the
guarantee is a property of the process rather than of the call site.

---

## 6. What is actually green

```
89 passed in 0.85s
```

Covering: rate governor fail-closed behaviour (13 cases), disk cache keying and
corruption (11), provenance and `input_hash` (13), the client end to end
against real bodies (26), and schema constraints (16).

**Spec test 5 (no lookahead) is green early.** It belongs to the schema, and a
constraint added after rows exist is a constraint that has already been
violated. It is enforced as a database CHECK and asserted through the ORM *and*
through a raw SQL insert that bypasses it.

Spec tests 1–4 and 6 are phases 2–4 and are not yet written.

### The end-to-end proof

```
python -m edgeloop.scripts.prove_ticker NVDA          # recorded bodies
python -m edgeloop.scripts.prove_ticker NVDA --live   # real HTTP, needs FMP_API_KEY
```

Cold run: **7 uncached calls — within the under-8 budget.** Second run: 0
uncached, 7 cached. It prints a full provenance record per fetch, the
point-in-time worked example, the missing register, the `input_hash`, and the
unverified-path list.

It deliberately prints **no forecast** — no mu, no sigma, no quantiles. There is
no quant core yet, and printing a number the system cannot stand behind is the
exact failure the ledger exists to prevent.

---

## Ready for review

Phase 1 is done. Before I start phase 2 I need a decision on §1 — specifically
whether `edgeloop2.jsx` exists somewhere I can't see, and how you want the four
sizing constraints defined given v1 isn't available.

Phase 2 (quant core + tests 1–4) does not depend on that answer. Phase 4
(sizing, portfolio) does.
