import { IMMUTABLE_GOVERNOR, ROBINHOOD_MCP_URL, stableHash } from "./governor.mjs";

export const OPERATIONAL_STATUS = Object.freeze([
  { label: "BUILT", state: "YES", detail: "Robinhood-native architecture, adaptive rehearsal engine, immutable governor, audit model, and control interface." },
  { label: "TESTED", state: "YES", detail: "Deterministic unit, temporal-validation, and adversarial governor tests run in the repository." },
  { label: "CONNECTED", state: "NO", detail: "Robinhood OAuth must be completed by the account owner on desktop." },
  { label: "SHADOW LIVE", state: "NO", detail: "Requires authenticated read-only MCP cycles against the dedicated Agentic account." },
  { label: "LIVE", state: "NO", detail: "Order placement is deliberately excluded from the current Codex tool allowlist." },
  { label: "AUTONOMOUS", state: "NO", detail: "Requires a hardened persistent execution enclave, durable state, monitoring, recovery, and earned capital authorization." },
]);

export const NOT_YET_IMPLEMENTED = Object.freeze([
  "Owner-completed Robinhood OAuth and Agentic-account onboarding",
  "Durable point-in-time market, forecast, order, and fill store",
  "Always-on execution enclave with its own Robinhood credential boundary",
  "Broker-event polling, crash recovery, alert delivery, and disaster runbook",
  "Shadow-live evidence and sequential promotion decision",
  "Owner risk mandate: capital ceiling and maximum permissible drawdown",
]);

export function systemManifest() {
  return {
    product: "EdgeLoop",
    version: "2.0.0-robinhood-native",
    broker: "Robinhood Agentic Trading",
    mcpUrl: ROBINHOOD_MCP_URL,
    apiKeyRequired: false,
    authentication: "Robinhood OAuth via Codex MCP host",
    portfolioSourceOfTruth: "Robinhood Trading MCP after authentication",
    currentMode: "LAB_LOCKED",
    executionEnabled: false,
    governorVersion: IMMUTABLE_GOVERNOR.version,
    governorHash: stableHash(IMMUTABLE_GOVERNOR),
    statuses: OPERATIONAL_STATUS,
    notYetImplemented: NOT_YET_IMPLEMENTED,
  };
}
