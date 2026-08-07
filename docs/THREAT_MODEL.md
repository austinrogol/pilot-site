# EdgeLoop threat model

## Safety invariants

- Robinhood is authoritative for brokerage state.
- Only the dedicated Agentic account may ever be traded.
- The intelligence process cannot call live placement tools in the current profile.
- The governor cannot be edited by research output or market content.
- Order submission is not evidence of a fill.
- Every action is idempotent and reconciled.
- Stale, missing, malformed, contradictory, or out-of-domain data fails closed.

## Adversaries and faults

- Prompt injection in news, filings, MCP output, or model-generated rationale.
- Tool/schema drift and changed Robinhood semantics.
- OAuth expiry or account rebinding.
- Duplicate schedules, retries, race conditions, and network partitions.
- Stale quotes, delayed fundamentals, and timestamp ambiguity.
- Corporate actions, fractional-share edge cases, and tax-lot mismatches.
- Partial fills, rejected orders, cancelled orders, and after-hours state changes.
- Selection bias, look-ahead, survivorship bias, overfitting, and regime collapse.
- Uncontrolled strategy mutation or silent risk-policy changes.

## Current mitigation

The automated red-team harness tests clean intent, stale quotes, wrong-account routing, duplicate intents, kill switch, margin/options/short escalation, missing review, price drift, buying-power races, drawdown breach, tool drift, order conflicts, contradictory state, out-of-domain regimes, and prompt injection inertness.

## Current gap

The hosted interface is not a secret-bearing execution runtime. A persistent execution enclave with durable state, credential isolation, broker polling, alerts, recovery, and deployment hardening is not yet implemented.

