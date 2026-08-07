import {
  TRADING_DAYS,
  clamp,
  deflatedSharpe,
  gaussian,
  mean,
  median,
  performanceMetrics,
  quantile,
  seededRandom,
  standardDeviation,
} from "./math.mjs";

const ASSETS = ["SIM-A", "SIM-B", "SIM-C", "SIM-D", "SIM-E", "SIM-F"];

function syntheticFixture(observations = 1260, seed = 20260807) {
  const random = seededRandom(seed);
  const prices = Object.fromEntries(ASSETS.map((asset) => [asset, [100]]));
  const spreadsBps = Object.fromEntries(ASSETS.map((asset, index) => [asset, 3 + index * 1.4]));
  const dollarAdv = Object.fromEntries(ASSETS.map((asset, index) => [asset, 900_000_000 / (1 + index * 0.42)]));
  for (let day = 1; day < observations; day += 1) {
    const regime = day < observations * 0.34 ? 0 : day < observations * 0.68 ? 1 : 2;
    const marketDrift = [0.00042, -0.00008, 0.00031][regime];
    const marketShock = gaussian(random) * [0.008, 0.014, 0.009][regime];
    ASSETS.forEach((asset, index) => {
      const persistentEdge = [0.00028, 0.00019, 0.00011, 0.00004, -0.00001, -0.00007][index];
      const regimeTilt = regime === 1 ? (index < 2 ? -0.00032 : 0.00012) : regime === 2 ? (index % 2 ? 0.0001 : -0.00003) : 0;
      const idiosyncratic = gaussian(random) * (0.006 + index * 0.0012);
      const returnValue = clamp(marketDrift + persistentEdge + regimeTilt + marketShock * (0.68 + index * 0.05) + idiosyncratic, -0.22, 0.22);
      prices[asset].push(prices[asset].at(-1) * Math.exp(returnValue));
    });
  }
  return { id: "SANITIZED-RESEARCH-FIXTURE", assets: ASSETS, prices, spreadsBps, dollarAdv, observations, seed };
}

function dailyReturns(prices, assets) {
  const length = Math.min(...assets.map((asset) => prices[asset].length));
  return Array.from({ length: length - 1 }, (_, index) => assets.map((asset) => prices[asset][index + 1] / prices[asset][index] - 1));
}

function standardize(values) {
  const center = mean(values);
  const sigma = standardDeviation(values);
  return sigma > 0 ? values.map((value) => (value - center) / sigma) : values.map(() => 0);
}

function normalizePositive(values) {
  const cleaned = values.map((value) => Math.max(0, Number.isFinite(value) ? value : 0));
  const total = cleaned.reduce((sum, value) => sum + value, 0);
  return total > 0 ? cleaned.map((value) => value / total) : cleaned.map(() => 0);
}

function adaptiveCandidates(observations) {
  const statisticallyAvailable = [20, 40, 63, 84, 126, 189, 252].filter((lookback) => lookback <= Math.floor(observations / 4));
  const complexityBudget = Math.max(2, Math.floor(Math.sqrt(Math.max(16, observations / TRADING_DAYS))));
  const lookbacks = statisticallyAvailable.filter((_, index) => index % Math.max(1, Math.ceil(statisticallyAvailable.length / (complexityBudget + 2))) === 0);
  const rebalanceDays = [5, 10, 21].filter((value) => value < Math.max(...lookbacks));
  const families = ["posterior-momentum", "trend-risk", "low-variance-carry"];
  const confidenceLevels = [0.68, 0.84, 0.95].slice(0, clamp(complexityBudget, 2, 3));
  const candidates = [];
  for (const family of families) {
    for (const lookback of lookbacks) {
      for (const rebalance of rebalanceDays) {
        for (const confidence of confidenceLevels) {
          candidates.push({ id: `${family.slice(0, 3).toUpperCase()}-${lookback}-${rebalance}-${Math.round(confidence * 100)}`, family, lookback, rebalance, confidence });
        }
      }
    }
  }
  return candidates;
}

function targetWeights(history, config) {
  const assetCount = history[0]?.length ?? 0;
  if (!assetCount) return [];
  const columns = Array.from({ length: assetCount }, (_, asset) => history.map((row) => row[asset]));
  const expected = columns.map((column) => mean(column));
  const uncertainty = columns.map((column) => standardDeviation(column) / Math.sqrt(Math.max(1, column.length)));
  const volatility = columns.map((column) => Math.max(1e-7, standardDeviation(column)));
  const z = config.confidence >= 0.95 ? 1.645 : config.confidence >= 0.84 ? 1 : 0.468;
  const lowerBounds = expected.map((value, index) => value - z * uncertainty[index]);
  const momentum = columns.map((column) => column.reduce((wealth, value) => wealth * (1 + value), 1) - 1);
  const momentumZ = standardize(momentum);
  const lowVolZ = standardize(volatility.map((value) => -value));
  let scores;
  if (config.family === "posterior-momentum") scores = lowerBounds.map((value, index) => Math.max(0, value) / volatility[index] + Math.max(0, momentumZ[index]) * 0.35);
  else if (config.family === "trend-risk") scores = momentumZ.map((value, index) => Math.max(0, value) / volatility[index]);
  else scores = lowVolZ.map((value, index) => Math.max(0, value + 0.35) * Math.max(0, lowerBounds[index] + uncertainty[index]) / volatility[index]);
  const raw = normalizePositive(scores);
  if (!raw.some((value) => value > 0)) return raw;
  const effectiveSignals = Math.max(1, raw.filter((value) => value > 0).length);
  const uncertaintyCap = clamp(1 / Math.sqrt(effectiveSignals), 0.18, 0.58);
  const capped = [...raw];
  for (let pass = 0; pass < assetCount * 2; pass += 1) {
    const excess = capped.reduce((sum, value) => sum + Math.max(0, value - uncertaintyCap), 0);
    capped.forEach((value, index) => { capped[index] = Math.min(value, uncertaintyCap); });
    const eligible = capped.map((value, index) => ({ value, index })).filter((item) => item.value < uncertaintyCap - 1e-9);
    const denominator = eligible.reduce((sum, item) => sum + Math.max(1e-9, raw[item.index]), 0);
    if (excess <= 1e-9 || !eligible.length || denominator <= 0) break;
    eligible.forEach((item) => { capped[item.index] += excess * Math.max(1e-9, raw[item.index]) / denominator; });
  }
  const confidenceDeployment = clamp(lowerBounds.filter((value) => value > 0).length / assetCount, 0, 1);
  return capped.map((value) => value * confidenceDeployment);
}

function backtest(fixture, config, start, end) {
  const rows = dailyReturns(fixture.prices, fixture.assets);
  const begin = Math.max(config.lookback, start);
  let weights = fixture.assets.map(() => 0);
  let turnover = 0;
  let costDrag = 0;
  const returns = [];
  for (let day = begin; day < Math.min(end, rows.length); day += 1) {
    if ((day - begin) % config.rebalance === 0) {
      const next = targetWeights(rows.slice(day - config.lookback, day), config);
      const trade = next.reduce((sum, value, index) => sum + Math.abs(value - weights[index]), 0);
      turnover += trade;
      const cost = next.reduce((sum, value, index) => {
        const change = Math.abs(value - weights[index]);
        const spread = fixture.spreadsBps[fixture.assets[index]] / 20_000;
        const participation = change * 1_000_000 / fixture.dollarAdv[fixture.assets[index]];
        return sum + change * (spread + 0.0012 * Math.sqrt(Math.max(0, participation)));
      }, 0);
      costDrag += cost;
      weights = next;
      const rawReturn = rows[day].reduce((sum, value, index) => sum + value * weights[index], 0);
      returns.push(rawReturn - cost);
    } else returns.push(rows[day].reduce((sum, value, index) => sum + value * weights[index], 0));
  }
  return { returns, weights, metrics: performanceMetrics(returns, turnover, costDrag) };
}

function buildFolds(observationCount) {
  const holdoutLength = Math.max(63, Math.floor(observationCount * 0.18));
  const holdoutStart = observationCount - holdoutLength;
  const minimumTraining = Math.max(252, Math.floor(observationCount * 0.36));
  const foldLength = Math.max(42, Math.floor((holdoutStart - minimumTraining) / 4));
  const folds = [];
  for (let end = minimumTraining + foldLength; end <= holdoutStart; end += foldLength) folds.push({ trainStart: 0, trainEnd: end - foldLength, validationStart: end - foldLength, validationEnd: end });
  return { folds, holdout: { start: holdoutStart, end: observationCount }, minimumTraining };
}

function rank(values, selected) {
  const sorted = [...values].sort((left, right) => right - left);
  return sorted.indexOf(selected) / Math.max(1, sorted.length - 1);
}

export function runAdaptiveRehearsal(options = {}) {
  const fixture = syntheticFixture(options.observations ?? 1260, options.seed ?? 20260807);
  const rows = dailyReturns(fixture.prices, fixture.assets);
  const split = buildFolds(rows.length);
  const configs = adaptiveCandidates(rows.length);
  const results = configs.map((config) => {
    const foldRuns = split.folds.map((fold) => backtest(fixture, config, fold.validationStart, fold.validationEnd));
    const foldGrowth = foldRuns.map((run) => run.metrics.geometricReturn);
    const validationReturns = foldRuns.flatMap((run) => run.returns);
    const trialSharpes = configs.length > 1 ? 1 / configs.length : 0;
    const selectionConfidence = deflatedSharpe(validationReturns, configs.length, trialSharpes);
    const validation = performanceMetrics(validationReturns, foldRuns.reduce((sum, run) => sum + run.metrics.turnover, 0), foldRuns.reduce((sum, run) => sum + run.metrics.costDrag, 0));
    const stability = foldGrowth.length ? median(foldGrowth) - (quantile(foldGrowth, 0.75) - quantile(foldGrowth, 0.25)) : -Infinity;
    return { config, foldRuns, foldGrowth, validationReturns, validation, selectionConfidence, stability };
  });
  let reversals = 0;
  for (let heldOut = 0; heldOut < split.folds.length; heldOut += 1) {
    const trainingScores = results.map((result) => median(result.foldGrowth.filter((_, index) => index !== heldOut)));
    const winnerIndex = trainingScores.indexOf(Math.max(...trainingScores));
    const outScores = results.map((result) => result.foldGrowth[heldOut]);
    if (rank(outScores, outScores[winnerIndex]) > 0.5) reversals += 1;
  }
  const pbo = split.folds.length ? reversals / split.folds.length : 1;
  const preselected = [...results].sort((left, right) => right.stability - left.stability);
  const survivors = [];
  const killed = [];
  preselected.forEach((result) => {
    const reasons = [];
    if (split.folds.length < 3) reasons.push("insufficient independent temporal folds");
    if (median(result.foldGrowth) <= 0) reasons.push("non-positive median walk-forward growth");
    if (result.foldGrowth.filter((value) => value > 0).length / Math.max(1, result.foldGrowth.length) < 0.6) reasons.push("unstable across temporal folds");
    if (result.selectionConfidence < 0.95) reasons.push("selection-adjusted Sharpe confidence below 95%");
    if (result.validation.maxDrawdown > 0.30) reasons.push("breached the laboratory drawdown envelope");
    if (pbo > 0.5) reasons.push("tournament probability of backtest overfitting exceeded 50%");
    (reasons.length ? killed : survivors).push({ ...result, reasons });
  });
  const provisional = survivors[0] ?? null;
  let champion = null;
  let holdout = null;
  if (provisional) {
    holdout = backtest(fixture, provisional.config, split.holdout.start, split.holdout.end);
    const holdoutConfidence = deflatedSharpe(holdout.returns, configs.length, 1 / Math.max(1, configs.length));
    const holdoutReasons = [];
    if (holdout.metrics.geometricReturn <= 0) holdoutReasons.push("untouched holdout geometric growth was non-positive");
    if (holdoutConfidence < 0.95) holdoutReasons.push("untouched holdout confidence was insufficient");
    if (holdout.metrics.maxDrawdown > 0.30) holdoutReasons.push("untouched holdout breached the laboratory drawdown envelope");
    if (!holdoutReasons.length) champion = { ...provisional, holdout, holdoutConfidence };
    else killed.push({ ...provisional, reasons: holdoutReasons, failedAt: "untouched holdout" });
  }
  return {
    id: `LAB-${fixture.seed}-${fixture.observations}`,
    fixture: fixture.id,
    createdAt: new Date(0).toISOString(),
    observations: rows.length,
    assets: fixture.assets.length,
    candidateCount: configs.length,
    foldCount: split.folds.length,
    holdoutObservations: split.holdout.end - split.holdout.start,
    pbo,
    survivors: champion ? survivors.length : 0,
    killRate: 1 - (champion ? survivors.length : 0) / Math.max(1, configs.length),
    champion: champion ? {
      id: champion.config.id,
      family: champion.config.family,
      lookback: champion.config.lookback,
      rebalance: champion.config.rebalance,
      validation: champion.validation,
      holdout: champion.holdout.metrics,
      selectionConfidence: champion.selectionConfidence,
      holdoutConfidence: champion.holdoutConfidence,
      terminalWeights: Object.fromEntries(fixture.assets.map((asset, index) => [asset, champion.holdout.weights[index] ?? 0])),
      cashWeight: Math.max(0, 1 - champion.holdout.weights.reduce((sum, value) => sum + value, 0)),
    } : null,
    killLedger: killed.slice(0, 12).map((result) => ({ id: result.config.id, family: result.config.family, reasons: result.reasons })),
    promotion: "LAB_ONLY",
    liveEligible: false,
    note: "Sanitized deterministic data proves the research machinery, not an investable edge. Robinhood point-in-time data and shadow evidence remain mandatory.",
  };
}

export function rehearsalSummary(result) {
  return {
    candidates: result.candidateCount,
    folds: result.foldCount,
    holdout: result.holdoutObservations,
    killed: result.candidateCount - result.survivors,
    pbo: result.pbo,
    decision: result.champion ? "SHADOW_CANDIDATE" : "NO_TRADE",
  };
}
