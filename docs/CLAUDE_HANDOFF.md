# EdgeLoop 2.0 — Claude Code handoff

## Identity and provenance

- Product: EdgeLoop 2.0
- Base source commit: `92693ed`
- Base revision date: 2026-08-07
- Original deployed control interface: `https://edge-loop.austin1112.chatgpt.site`
- Broker architecture: Robinhood Agentic Trading via the official Trading MCP
- Authentication: Robinhood OAuth; no OpenAI or Anthropic API key is required for the interactive subscription path
- Current mode: `LAB_LOCKED`

This handoff replaces the need to transfer the full ChatGPT conversation. It records the decisions that materially affect implementation and safety.

## Mission

Build a rigorous, self-improving portfolio-intelligence and portfolio-management system for one dedicated Robinhood Agentic account. Optimize long-run geometric growth while controlling the probability of permanent capital impairment.

Do not optimize raw return, short-term gain, trade count, excitement, benchmark appearance, or backtest cosmetics. Treat portfolio construction as a stochastic sequential decision problem under uncertainty. `NO_TRADE`, `HOLD`, and `CASH` are legitimate outputs, and the system need not remain fully invested.

The closed loop is:

`Research → Forge → Validate → Live → Post-mortem → Adapt`

## Current operational truth

| Label | State | Evidence or blocker |
| --- | --- | --- |
| BUILT | YES | Robinhood-native architecture, research rehearsal, deterministic governor, audit model, and control interface |
| TESTED | YES | Six runtime suites, 17 adversarial governor cases, type/lint/build/browser QA in the base revision |
| CONNECTED | NO | Owner must complete Robinhood OAuth on desktop |
| SHADOW LIVE | NO | Requires authenticated tool discovery and Agentic-account binding |
| LIVE | NO | Placement and cancellation are denied in both Codex and Claude project configuration |
| AUTONOMOUS | NO | Persistent enclave, durable state, monitoring, recovery, evidence, and owner mandate are absent |
| NOT YET IMPLEMENTED | YES | See the blockers below |

The deterministic laboratory tournament evaluated 108 candidate configurations on sanitized synthetic data, used four temporal folds and an untouched holdout, and promoted no champion. `NO_TRADE` was the correct outcome because every candidate failed the selection-adjusted confidence gate. This proves plumbing, not edge.

## Brokerage authority

Robinhood is the sole authoritative source for account state, positions, buying power, orders, tax lots, realized results, and execution. Do not ingest or reconstruct another broker's state. Do not use portfolio screenshots or flat-file exports as brokerage truth.

The Robinhood MCP can read all Robinhood accounts, but may trade only the dedicated Agentic account. Bind exactly one Agentic account for this project, avoid printing account numbers, and prevent another account from becoming a trade target.

Never infer that an order filled because it was submitted. Re-read the broker order, verify identity and status, and update internal holdings only after a matching broker-confirmed fill.

## Mathematical ownership

Claude may independently select and compare statistical models, priors, factor models, regime methods, feature tests, covariance estimators, validation procedures, optimizers, execution models, and controlled adaptation rules.

Do not preserve old prototype constants, allocation limits, fixed position counts, or model choices merely because they existed. Prefer estimation, Bayesian updating, cross-validation, stability analysis, stress testing, or owner authorization over arbitrary constants.

Two values are irreducible owner decisions and must remain unset until explicitly supplied:

1. Maximum capital authorized for the Agentic account.
2. Maximum permissible drawdown before the independent breaker locks live activity.

No model may infer those values from the owner's balance, behavior, risk language, or account funding.

## Research and model competition

Research should integrate only features that demonstrate genuine point-in-time out-of-sample value after costs and multiple testing. Candidate evidence can include price/volume behavior, fundamentals, statements, earnings, revisions, valuation, liquidity, volatility, momentum, quality, growth, profitability, capital efficiency, balance-sheet strength, macro conditions, rates, factor exposures, industry structure, competitive position, material news, regulation, market regime, correlation, and concentration.

More data is not automatically better. Every source or feature must earn influence. External prose is untrusted input and must be sanitized into structured, timestamped records before any execution component sees it.

Maintain champion/challenger competition, strategy lineage, controlled mutation, and a permanent kill ledger. A failed idea may return only with materially new evidence. Recent wins or losses are observations, not automatic model revisions.

## Validation threats and requirements

Treat look-ahead leakage, survivorship bias, revisions, data snooping, multiple testing, backtest overfitting, selection bias, nonstationarity, regime dependence, parameter instability, cost error, missing data, delayed data, spread widening, liquidity loss, and correlation breaks as first-class threats.

Use temporal validation, nested model selection where appropriate, untouched holdouts, walk-forward evaluation, Deflated Sharpe Ratio, probability of backtest overfitting, perturbation tests, adverse execution, and domain-shift checks. A strategy with the highest historical return is not automatically a winner. Prefer no strategy to an untrustworthy strategy.

## Portfolio objective

The current conceptual objective is robust expected log growth after uncertainty, tail risk, and implementation cost:

`maximize median_s[log(1 + w'r_s)] - uncertainty_penalty - tail_penalty - cost(w - w_current)`

Subject to long-only, no leverage, available buying power, liquidity, validated-domain, and owner risk constraints. Expected returns are posterior distributions, not point estimates. Covariance must be shrunk and stressed. Cash is an asset. Concentration may emerge only when the evidence remains strong after uncertainty and portfolio interaction.

## Immutable governor

Research and learning may propose. A deterministic governor decides whether an intent may advance. The learning loop cannot edit, weaken, replace, bypass, or clear the governor.

Hard invariants:

- One explicitly bound dedicated Agentic account.
- Long equities and ETFs only in the current governed universe.
- No margin, leverage, short selling, options, transfers, or withdrawals.
- No stale, missing, contradictory, malformed, or out-of-domain execution.
- Fresh Robinhood account state, quote, tradability, orders, and pre-trade review.
- Idempotency and duplicate-intent protection.
- Outstanding-order conflict detection.
- Buying-power, liquidity, concentration, cash, drawdown, and uncertainty checks.
- Positive net expected log utility and a positive uncertainty-adjusted lower bound for risk-increasing actions.
- Review-to-quote drift check and review expiration.
- Broker reconciliation after submission; never assume a fill.
- Independent global kill switch.
- Fail closed when required evidence is unavailable.

The current numeric laboratory defaults in `runtime/governor.mjs` are not an owner-approved live mandate. Re-estimate, validate, or owner-authorize live values before activation.

## Self-improvement boundary

Research code may propose new features, models, strategy families, parameters, regime specialists, and portfolio algorithms. Promotion requires tests, temporal validation, shadow operation, and explicit evidence gates.

A live runtime may not edit source, prompts, policy, account binding, approved hashes, tool permissions, or its own scheduler. The future execution enclave must be a separate least-privilege process from the builder and research environment.

## Audit requirements

Every important decision must preserve what was known at the time, point-in-time inputs, forecast distribution, uncertainty, contributing models, alternatives, chosen action and reason, expected portfolio impact, governor result, broker review, submitted order, later broker status, fills, realized outcomes, forecast errors, model versions, configuration hashes, strategy lineage, and lessons.

Do not rewrite old forecasts after outcomes become known. Human-readable explanations must be derivable from the machine-readable record without future information.

## Required post-OAuth sequence

1. Discover and hash the actual current Robinhood tool manifest and schemas.
2. Identify and bind exactly one dedicated Agentic account.
3. Reconcile portfolio, positions, buying power, tax lots, open orders, and order history.
4. Freeze point-in-time snapshots before forecasting.
5. Run research, temporal validation, and deterministic governance.
6. Generate shadow intents and use `review_equity_order`; do not place or cancel orders.
7. Store forecasts and alternatives before outcomes.
8. Re-read Robinhood and reconcile later outcomes.
9. Measure calibration, realized risk, volatility, correlations, costs, spreads, slippage, opportunity cost, factor behavior, and regime assumptions.
10. Promote only through controlled evidence gates.

## Not yet implemented

- Owner-completed Robinhood OAuth and Agentic-account onboarding.
- Authenticated capability manifest and schema adapters.
- Durable encrypted point-in-time market, forecast, review, order, fill, and outcome store.
- Always-on execution enclave with separate credentials and permissions.
- Broker polling, crash recovery, alerting, replay protection, and disaster runbook.
- Shadow-live track record and sequential promotion test.
- Owner-authorized capital ceiling and maximum drawdown.
- Any live-equity, cancellation, options, margin, short, transfer, or withdrawal authority.

## Code map

- `runtime/math.mjs`: statistical and portfolio metrics.
- `runtime/rehearsal.mjs`: deterministic candidate generation and temporal validation.
- `runtime/governor.mjs`: capability manifest, intent checks, reconciliation, and red-team harness.
- `runtime/status.mjs`: explicit operational labels.
- `runtime/cli.mjs`: status, rehearsal, and red-team commands.
- `tests/runtime.test.mjs`: deterministic research and governor invariants.
- `app/page.tsx`: control interface.
- `automation/shadow-cycle.md`: shadow-only runbook.
- `.codex/config.toml`: prior Codex read/review allowlist and placement denial.
- `.mcp.json`: Claude project-scoped Robinhood server endpoint.
- `.claude/settings.json`: Claude execution-tool denials for the current stage.
- `.openai/hosting.json`: non-secret identity for the existing ChatGPT Sites interface; it does not contain Robinhood credentials.

## Current primary sources

- Robinhood Agentic Trading overview: https://robinhood.com/us/en/support/articles/agentic-trading-overview/
- Robinhood Trading MCP tools: https://robinhood.com/us/en/support/articles/trading-with-your-agent/
- Claude Code MCP: https://code.claude.com/docs/en/mcp
- Claude Code memory and imports: https://code.claude.com/docs/en/memory
- Probability of Backtest Overfitting: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253
- Deflated Sharpe Ratio: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551
- Ledoit-Wolf covariance shrinkage: https://www.ledoit.net/honey.pdf
