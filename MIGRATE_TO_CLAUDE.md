# Move EdgeLoop to Claude Code

## What transfers

The repository transfers source code, tests, architecture, operating constraints, status, MCP configuration, and the important decisions from the ChatGPT/Codex work. Chat transcripts and hidden product memory do not automatically transfer between providers. The durable context is therefore encoded in `CLAUDE.md`, `AGENTS.md`, and `docs/CLAUDE_HANDOFF.md`.

Do not copy OAuth tokens, account numbers, passwords, two-factor codes, `.env` files, `~/.claude.json`, or ChatGPT/Codex credential files into GitHub.

## Recommended repository

Create a new **private** GitHub repository named `edge-loop`. Do not put EdgeLoop into `pilot-site` unless you intentionally want to replace that unrelated project.

Unzip this bundle into the new repository and push it:

```bash
git init
git add .
git commit -m "Import EdgeLoop 2.0 handoff"
git branch -M main
git remote add origin git@github.com:austinrogol/edge-loop.git
git push -u origin main
```

If the repository URL differs, use the exact URL GitHub gives you.

## Import the Codex project contract

Claude Code 2.1.213 or newer can import configuration from coding agents. From the repository root:

```bash
claude import codex --dry-run
claude import codex
```

The repository already contains a purpose-built `CLAUDE.md`, so inspect the import diff and do not accept duplicated or contradictory rules. `CLAUDE.md` imports the existing `AGENTS.md` and the full EdgeLoop handoff.

Then start Claude Code:

```bash
claude
```

Inside the session:

1. Accept workspace trust for this private repository.
2. Run `/context` and verify `CLAUDE.md`, `AGENTS.md`, and `docs/CLAUDE_HANDOFF.md` are loaded.
3. Run `/doctor` if Claude reports configuration problems.
4. Run the tests before changing architecture.

## Connect Robinhood and open the Agentic account

This must be completed on a **desktop**. Robinhood does not permit Agentic-account onboarding or agent authentication solely from a phone.

The repository contains a project-scoped `.mcp.json` with Robinhood's official endpoint. In Claude Code:

1. Run `/mcp`.
2. Approve the project-scoped `robinhood-trading` server.
3. Select it and authenticate.
4. Complete Robinhood's on-screen Agentic-account onboarding.

Equivalent terminal setup for a repository without `.mcp.json`:

```bash
claude mcp add --transport http robinhood-trading --scope project https://agent.robinhood.com/mcp/trading
claude mcp login robinhood-trading
```

Robinhood requires an existing primary individual investing account in good standing. During authentication, Robinhood prompts you to create the additional dedicated Agentic account.

## First Claude instruction after authentication

Paste this into Claude Code:

```text
Read CLAUDE.md, AGENTS.md, docs/CLAUDE_HANDOFF.md, docs/ARCHITECTURE.md,
docs/THREAT_MODEL.md, and docs/STATUS.md. Run /context and report which
instructions loaded. Inspect the actual authenticated robinhood-trading MCP
manifest and document the exact current tool schemas. Remain LAB_LOCKED.
Do not call place_equity_order, cancel_equity_order, place_option_order, or
cancel_option_order. Identify the dedicated Agentic account without printing
account numbers. Reconcile accounts, Agentic-account portfolio, positions,
buying power, tax lots, and open orders using Robinhood as the only brokerage
source of truth. Run the repository tests. Then produce a gap report for the
read-only shadow-live stage. Do not modify the governor or permission denials.
```

## Safe progression

1. Authenticate and create the empty Agentic account.
2. Discover and hash current Robinhood tool schemas.
3. Bind exactly one Agentic account while minimizing account-identifying output.
4. Run read-only reconciliation and shadow decisions.
5. Preserve point-in-time forecasts and compare them with later outcomes.
6. Accumulate enough shadow evidence to assess calibration, costs, drift, and reliability.
7. Build and independently review a persistent execution enclave.
8. Ask the owner for the capital ceiling and maximum permissible drawdown.
9. Only after every gate passes should a separate live configuration be considered.

Creating the Agentic account is not permission to trade. Do not fund it materially or remove the checked-in execution denials merely because OAuth succeeded.

## Phone versus desktop

The Claude mobile Code interface can continue working on the GitHub repository after setup. It is not the right place for the initial Robinhood authorization, and it is not an always-on execution runtime. Continuous operation eventually needs a persistent host, scheduler, encrypted durable state, health monitoring, alerting, crash recovery, and an independent kill switch.
