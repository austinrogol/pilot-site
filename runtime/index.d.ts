export type MetricSet = {
  observations: number;
  geometricReturn: number;
  annualVolatility: number;
  sharpe: number;
  sortino: number;
  maxDrawdown: number;
  cvar95: number;
  hitRate: number;
  turnover: number;
  costDrag: number;
  terminalWealth: number;
};

export type RehearsalResult = {
  id: string;
  fixture: string;
  observations: number;
  assets: number;
  candidateCount: number;
  foldCount: number;
  holdoutObservations: number;
  pbo: number;
  survivors: number;
  killRate: number;
  champion: null | {
    id: string;
    family: string;
    lookback: number;
    rebalance: number;
    validation: MetricSet;
    holdout: MetricSet;
    selectionConfidence: number;
    holdoutConfidence: number;
    terminalWeights: Record<string, number>;
    cashWeight: number;
  };
  killLedger: Array<{ id: string; family: string; reasons: string[] }>;
  promotion: string;
  liveEligible: boolean;
  note: string;
};

export function runAdaptiveRehearsal(options?: { observations?: number; seed?: number }): RehearsalResult;
export function runRedTeamHarness(): {
  total: number;
  passed: number;
  failed: number;
  results: Array<{ name: string; expected: string; observed: string; passed: boolean; blockers: string[] }>;
  policyHash: string;
  invariant: string;
};
