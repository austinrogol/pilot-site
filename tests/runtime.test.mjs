import assert from "node:assert/strict";
import test from "node:test";

import {
  EXECUTION_TOOLS,
  REQUIRED_READ_TOOLS,
  capabilityManifest,
  evaluateOrderIntent,
  reconcileExecution,
  runRedTeamHarness,
} from "../runtime/governor.mjs";
import { runAdaptiveRehearsal } from "../runtime/rehearsal.mjs";
import { systemManifest } from "../runtime/status.mjs";

test("adaptive research is deterministic, temporally gated, and never self-promotes", () => {
  const first = runAdaptiveRehearsal();
  const second = runAdaptiveRehearsal();

  assert.deepEqual(first, second);
  assert.equal(first.fixture, "SANITIZED-RESEARCH-FIXTURE");
  assert.ok(first.candidateCount > 0);
  assert.notEqual(first.candidateCount, 486);
  assert.ok(first.foldCount >= 3);
  assert.ok(first.holdoutObservations > 0);
  assert.equal(first.promotion, "LAB_ONLY");
  assert.equal(first.liveEligible, false);
});

test("capability discovery separates research readiness from execution authority", () => {
  const readOnly = capabilityManifest(REQUIRED_READ_TOOLS);
  assert.equal(readOnly.readReady, true);
  assert.equal(readOnly.reviewReady, true);
  assert.equal(readOnly.executionAdvertised, false);

  const full = capabilityManifest([...REQUIRED_READ_TOOLS, ...EXECUTION_TOOLS]);
  assert.equal(full.executionAdvertised, true);
  assert.notEqual(full.schemaHash, readOnly.schemaHash);
});

test("the governor fails closed without the owner risk mandate and live activation", () => {
  const now = Date.UTC(2026, 7, 7, 16, 0, 0);
  const result = evaluateOrderIntent(
    {
      id: "intent-test",
      idempotencyKey: "cycle-test",
      assetClass: "equity",
      side: "buy",
      quantity: 1,
      notional: 100,
      fractional: false,
      usesMargin: false,
      riskIncreasing: true,
      postTradeWeight: 0.01,
      postTradeCashWeight: 0.99,
      netUtilityDelta: 0.01,
      expectedLogReturnLowerBound: 0.001,
    },
    {
      now,
      mode: "LAB_LOCKED",
      killSwitch: false,
      boundAgenticAccountId: "agentic-test",
      account: { id: "agentic-test", isAgentic: true, buyingPower: 1_000, equity: 1_000 },
      accountAsOf: new Date(now).toISOString(),
      quote: { mid: 100, asOf: new Date(now).toISOString() },
      review: { accepted: true, referencePrice: 100, asOf: new Date(now).toISOString() },
      tradability: { tradable: true, fractional: true },
      capabilities: capabilityManifest(REQUIRED_READ_TOOLS),
      outstandingOrderConflict: false,
      seenIntentIds: [],
      seenIdempotencyKeys: [],
      stateConsistent: true,
      modelDomainDistance: 0,
      maximumValidatedDomainDistance: 1,
      riskMandate: null,
    },
  );

  assert.equal(result.decision, "BLOCK");
  assert.ok(result.failures.some(({ code }) => code === "OWNER_RISK_MANDATE_MISSING"));
  assert.ok(result.failures.some(({ code }) => code === "NOT_LIVE_MODE"));
});

test("internal holdings can change only after a matching broker-confirmed fill", () => {
  const pending = reconcileExecution(
    { brokerOrderId: "rh-order-1" },
    { id: "rh-order-1", status: "queued", filledQuantity: 0 },
  );
  assert.equal(pending.reconciled, true);
  assert.equal(pending.mayUpdateInternalPortfolio, false);

  const mismatch = reconcileExecution(
    { brokerOrderId: "rh-order-1" },
    { id: "rh-order-2", status: "filled", filledQuantity: 1 },
  );
  assert.equal(mismatch.reconciled, false);

  const filled = reconcileExecution(
    { brokerOrderId: "rh-order-1" },
    { id: "rh-order-1", status: "filled", filledQuantity: 1, averageFillPrice: 101.25 },
  );
  assert.equal(filled.mayUpdateInternalPortfolio, true);
  assert.equal(filled.averageFillPrice, 101.25);
});

test("adversarial harness blocks every attack while treating injected prose as inert data", () => {
  const harness = runRedTeamHarness();
  assert.equal(harness.total, 17);
  assert.equal(harness.passed, harness.total);
  assert.equal(harness.failed, 0);
  assert.equal(harness.results.find(({ name }) => name === "prompt injection remains inert")?.observed, "ALLOW");
});

test("the published manifest cannot claim connectivity, live trading, or autonomy", () => {
  const manifest = systemManifest();
  assert.equal(manifest.apiKeyRequired, false);
  assert.equal(manifest.currentMode, "LAB_LOCKED");
  assert.equal(manifest.executionEnabled, false);
  for (const label of ["CONNECTED", "SHADOW LIVE", "LIVE", "AUTONOMOUS"]) {
    assert.equal(manifest.statuses.find((status) => status.label === label)?.state, "NO");
  }
});
