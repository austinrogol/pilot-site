# EdgeLoop 2.0

Robinhood-native quantitative portfolio intelligence and governance research system.

EdgeLoop targets long-run geometric growth while controlling the probability of permanent capital impairment. `CASH`, `HOLD`, and `NO_TRADE` are first-class decisions. The operating loop is:

`Research → Forge → Validate → Live → Post-mortem → Adapt`

## Current truth

| Capability | State |
| --- | --- |
| Architecture, research rehearsal, governor, audit model, and interface | BUILT |
| Runtime, type, lint, build, and browser checks | TESTED |
| Robinhood OAuth | NOT CONNECTED |
| Dedicated Agentic account binding | NOT CONNECTED |
| Shadow-live evidence | NOT STARTED |
| Live order placement | DISABLED |
| Persistent autonomous execution | NOT IMPLEMENTED |

No live order has been submitted by this repository. The checked-in Claude settings deny Robinhood equity and option placement/cancellation tools.

## Claude Code setup

Read [MIGRATE_TO_CLAUDE.md](MIGRATE_TO_CLAUDE.md), then open this repository in Claude Code. Claude loads `CLAUDE.md`, which imports the operating contract and detailed handoff.

On a desktop:

```bash
npm ci
npm run test:runtime
npm run lint
claude
```

Inside Claude Code, run `/context` to verify the instructions loaded and `/mcp` to approve and authenticate the official Robinhood server. Robinhood requires desktop onboarding.

## Primary code

- `runtime/math.mjs` — quantitative utilities and shrinkage/statistical metrics
- `runtime/rehearsal.mjs` — deterministic adaptive research tournament
- `runtime/governor.mjs` — fail-closed order-intent governor and reconciliation
- `runtime/status.mjs` — truthful operational manifest
- `tests/runtime.test.mjs` — research, capability, reconciliation, and adversarial tests
- `app/` — monitoring and control interface
- `docs/` — architecture, threat model, status, and Claude handoff

## Safety boundary

Research logic may evolve. Account binding, execution permissions, the kill switch, audit integrity, and the deterministic governor may not silently rewrite themselves. Live activation requires a separate reviewed execution enclave, durable state, shadow evidence, and the owner's capital ceiling and maximum permissible drawdown.
