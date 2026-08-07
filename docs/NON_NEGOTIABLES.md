# Non-negotiables

These came out of testing, not taste. Each one names where it is enforced, so
"is this still true?" is a question you can answer by reading code rather than
by trusting this document.

Do not relax any of them without evidence.

---

## 1. No directional forecast at or under 21 days

The equity risk premium is roughly 0.02%/day against a single-name daily sigma
near 2%. That is a signal-to-noise ratio around 1:100. At horizons ≤21 days,
drift is the market-implied CAPM rate and nothing else. No momentum tilt, no
sentiment overlay, no analyst-revision signal.

What the system forecasts at short horizons is **dispersion**, because
volatility clustering replicates and direction does not.

| Enforced | Where |
|---|---|
| Boundary is config, not a literal | `config.py` → `DriftPriors.no_forecast_horizon_days` |
| Analyst data is fetched but flagged non-input | `data/endpoints.py` → `grades`, `price_target_consensus` notes |
| News is stored, never scored | `data/endpoints.py` → `news_stock` note |
| `drift_source` is recorded per forecast | `data/models.py` → `Forecast.drift_source` |
| Docstring so nobody quietly adds a signal | `quant/drift.py` *(phase 2)* |

## 2. Distributions, never point targets

Every forecast is a set of quantiles plus the parameters that generated them.
If a function returns a single expected price, it is wrong.

| Enforced | Where |
|---|---|
| No `expected_price` column exists, and a test asserts it never appears | `data/models.py`, `tests/test_schema_constraints.py::test_there_is_no_expected_price_column` |
| Quantile ordering is a DB constraint | `ck_forecasts_quantiles_ordered` |
| `p_positive` must be a probability | `ck_forecasts_p_positive_is_probability` |

## 3. GARCH must pass an identification test before its output is used

On short samples the fit runs to the parameter boundary and prints a volatility
half-life that is pure artifact. **Verified: 47 NVDA returns pinned alpha and
beta to both grid edges and produced a 1.4-day half-life that means nothing.**

Use `arch` and check the parameter t-statistics. If alpha or beta is
insignificant, or n < 150, reject the fit, fall back to EWMA with flat
sqrt-time scaling, and record the rejection reason in the forecast row.

A featureless term structure is the honest output for a thin sample.

| Enforced | Where |
|---|---|
| Thresholds are config | `config.py` → `VolatilityConfig.min_observations`, `min_param_tstat` |
| A rejected fit must carry a reason; an accepted one must not | `ck_forecasts_rejection_reason_iff_rejected` |
| Identification test itself | `quant/volatility.py` *(phase 2)* |

## 4. Calibration stays empty until it's real

No coverage stat is reported below 30 resolved forecasts per horizon. Never
display a backtest in a place a user could read as a track record.

**The ledger starts empty and that is correct.**

| Enforced | Where |
|---|---|
| Gate is config | `config.py` → `LedgerConfig.min_resolved_for_calibration` |
| Coverage reported only with its binomial CI | `ledger/calibration.py` *(phase 3)* |

## 5. Missing data is null and logged, never inferred

Any field the source didn't return goes in a `missing[]` list that surfaces to
the UI. No interpolation, no "reasonable estimate," no carrying a stale value
forward silently.

| Enforced | Where |
|---|---|
| The register itself | `data/provenance.py` → `Provenance.missing`, `MissingField` |
| Every optional field defaults to `None`, never to a value | `data/schemas.py` |
| Callers declare the fields they depend on | `data/fmp.py` → `expect_fields` |
| A stale cache read is labelled `Quality.STALE` with its age | `data/fmp.py` |
| Plan-gated data raises instead of returning empty | `data/endpoints.py` → `EndpointBlocked` |
| `require_first()` refuses to substitute a default | `data/fmp.py` |

Note the word *silently*. Serving an expired cache entry when the rate governor
refuses a refetch is permitted — it is labelled at every layer up to the UI.
Failing an entire analysis because a budget ran out throws away good data for
no gain.

## 6. Point-in-time discipline everywhere

Every stored record carries the timestamp of the data, not just the fetch.
Fundamentals get their filing date. This is what makes a future backtest
legitimate instead of leaked. Design for it now even though nothing backtests
yet.

**Worked example from the live data:** NVDA's FY2026 income statement has
`date` = 2026-01-25 (fiscal period end) and `acceptedDate` = 2026-02-25 (SEC
acceptance). A backtest keyed on `date` would trade on that filing **31 days
before it existed**.

| Enforced | Where |
|---|---|
| `data_asof` separate from `fetched_at` on every record | `data/provenance.py` |
| `as_of()` returns acceptance, never the period end — and returns `None` rather than falling back | `data/schemas.py` → `IncomeStatement.as_of` |
| A provenance record that postdates its fetch is refused at construction | `data/provenance.py.__post_init__` |
| **Database** CHECK, not a code convention | `ck_forecasts_no_lookahead`, `ck_provenance_no_lookahead` |
| Spec test 5 | `tests/test_schema_constraints.py::TestNoLookahead` |

---

## Out of scope — do not build

Each is either unsourceable or already tested and rejected.

- **Alternative data** (web traffic, app installs, card panels, job postings).
  Credible vendors start in the tens of thousands per year. Scraped substitutes
  are unreliable and usually violate terms.
- **Options-implied anything.** No data source — see below.
- **News sentiment scoring.** The desk-trading research lab already rejected
  eight price-based signals and four alt-data regime models as unable to beat
  SPY. Do not re-run that experiment in a new costume.
- **Automated strategy generation** or a self-modifying strategy pool.
- **Any order execution or brokerage write access.** This system is read-only
  and advisory. Full stop.

## The options gap

FMP sells no options data at **any** tier: no chains, no implied vol, no skew,
no open interest. `VolatilitySource` gets a `RealizedVol` implementation and the
`ImpliedVol` slot stays empty with an explicit `NotImplementedError`.

This is the single largest gap in the system and it is kept visible in code
(`data/endpoints.py` → `OPTIONS_AVAILABILITY`) rather than buried.
