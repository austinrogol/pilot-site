@AGENTS.md
@docs/CLAUDE_HANDOFF.md

# Claude Code operating notes

- Begin every session by checking the current repository state and `docs/STATUS.md`.
- Run `/context` after first opening the repository to verify this file and its imports loaded.
- Default to `LAB_LOCKED`. Do not place or cancel Robinhood orders.
- The committed `.claude/settings.json` denial rules are a safety boundary, not an inconvenience to route around.
- Use only Robinhood's official Trading MCP as brokerage authority. Do not reconstruct brokerage state from screenshots, exports, memory, or another broker.
- Discover the authenticated MCP tool manifest before implementing adapters. Do not guess tool schemas.
- Never silently convert a laboratory metric, synthetic result, or model narrative into live evidence.
- Do not revive old fixed allocation rules or numerical thresholds merely because they appeared in prior prototypes. Estimate, validate, stress, or owner-authorize important parameters.
- The owner alone must set the capital ceiling and maximum permissible drawdown. Do not infer either.
- Builder sessions may edit code. A future live runtime must be a separate least-privilege process that cannot edit source, prompts, policy, approved hashes, or permissions.
- Before claiming progress, use the exact labels: `BUILT`, `TESTED`, `CONNECTED`, `SHADOW LIVE`, `LIVE`, `AUTONOMOUS`, or `NOT YET IMPLEMENTED`.
- `NO_TRADE`, `HOLD`, and `CASH` are valid outcomes. Never force activity to make a demonstration look successful.
- Required checks after code changes: `npm run test:runtime`, `npm run lint`, and the relevant build/type checks.
