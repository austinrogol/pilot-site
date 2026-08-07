# EdgeLoop 2.0 — Robinhood-native architecture

## Mission

Maximize long-run geometric growth subject to explicit owner risk limits and a hardened probability-of-ruin constraint. Cash, hold, and no-trade are first-class decisions.

## Planes

1. **Robinhood authority plane** — official Trading MCP supplies account inventory, Agentic-account state, positions, tax lots, buying power, quotes, order book, order review, order status, and fills.
2. **Research plane** — point-in-time features, competing models, regime inference, uncertainty distributions, and source provenance. External text is untrusted input.
3. **Validation plane** — nested walk-forward evaluation, untouched holdout, cost/liquidity perturbations, fold stability, Deflated Sharpe Ratio, probability of backtest overfitting, and kill ledger.
4. **Portfolio plane** — robust expected-log-growth optimization with posterior uncertainty, covariance shrinkage, cash as an asset, transaction costs, and portfolio-level marginal risk.
5. **Governor plane** — deterministic separate authority. It validates account scope, data freshness, tool manifest, buying power, liquidity, concentration, drawdown, model domain, duplicate intents, order conflicts, review freshness, and kill switches.
6. **Execution plane** — eventual two-phase review → governed place → broker reconciliation. It must not infer fills from submissions.
7. **Audit plane** — append-only snapshots, forecasts, alternatives, decisions, interventions, reviews, orders, fills, outcomes, model lineage, and policy hashes.
8. **Control plane** — human-readable monitoring interface and owner kill switch.

## Mathematical objective

For posterior return scenarios `r_s`, candidate post-trade weights `w`, trading cost `C`, and owner-defined tail limits, the portfolio engine targets:

`maximize median_s[log(1 + w′r_s)] − uncertainty_penalty − tail_penalty − C(w − w_current)`

subject to long-only, no leverage, broker buying power, liquidity/participation, validated-domain, and owner risk constraints. Expected-return estimates are shrunk toward defensible priors; covariance is shrunk and stressed; increasingly concentrated allocations require increasingly strong posterior evidence.

No fixed position count or inherited weight cap is assumed. Sparsity, cash, and concentration emerge from uncertainty, costs, covariance, liquidity, and the owner mandate.

## Controlled adaptation

Research code may propose new features, models, mutations, and strategy families. A proposal must pass tests, temporal validation, shadow operation, and an explicit promotion gate. The governor, tool policy, account binding, and deployment permissions are immutable to the learning loop.

## No-key runtime path

The repository contains a project-scoped Codex MCP configuration using Robinhood OAuth and a shadow-cycle runbook. OpenAI scheduled tasks can run a local project when the desktop app and project remain available. This is suitable for research/shadow operation, not yet a hardened always-on live execution service.

## Production state still required

Before live capital: owner OAuth/onboarding, exact tool-schema discovery, durable encrypted state, an independently permissioned execution enclave, monitoring and recovery, shadow-live evidence, capital ceiling, maximum tolerated drawdown, and an explicit activation event.

