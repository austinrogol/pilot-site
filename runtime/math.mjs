export const TRADING_DAYS = 252;

export function clamp(value, lower, upper) {
  return Math.min(upper, Math.max(lower, value));
}

export function mean(values) {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
}

export function variance(values, sample = true) {
  if (values.length < (sample ? 2 : 1)) return 0;
  const center = mean(values);
  const denominator = sample ? values.length - 1 : values.length;
  return values.reduce((sum, value) => sum + (value - center) ** 2, 0) / denominator;
}

export function standardDeviation(values) {
  return Math.sqrt(Math.max(0, variance(values)));
}

export function quantile(values, probability) {
  if (!values.length) return 0;
  const sorted = [...values].sort((left, right) => left - right);
  const index = clamp(probability, 0, 1) * (sorted.length - 1);
  const lower = Math.floor(index);
  const upper = Math.ceil(index);
  if (lower === upper) return sorted[lower];
  return sorted[lower] + (sorted[upper] - sorted[lower]) * (index - lower);
}

export function median(values) {
  return quantile(values, 0.5);
}

export function normalCdf(value) {
  const sign = value < 0 ? -1 : 1;
  const x = Math.abs(value) / Math.sqrt(2);
  const t = 1 / (1 + 0.3275911 * x);
  const coefficients = [0.254829592, -0.284496736, 1.421413741, -1.453152027, 1.061405429];
  const polynomial = (((((coefficients[4] * t + coefficients[3]) * t) + coefficients[2]) * t + coefficients[1]) * t + coefficients[0]) * t;
  const erf = sign * (1 - polynomial * Math.exp(-x * x));
  return 0.5 * (1 + erf);
}

export function inverseNormal(probability) {
  const p = clamp(probability, 1e-12, 1 - 1e-12);
  const a = [-39.6968302866538, 220.946098424521, -275.928510446969, 138.357751867269, -30.6647980661472, 2.50662827745924];
  const b = [-54.4760987982241, 161.585836858041, -155.698979859887, 66.8013118877197, -13.2806815528857];
  const c = [-0.00778489400243029, -0.322396458041136, -2.40075827716184, -2.54973253934373, 4.37466414146497, 2.93816398269878];
  const d = [0.00778469570904146, 0.32246712907004, 2.445134137143, 3.75440866190742];
  const low = 0.02425;
  const high = 1 - low;
  if (p < low) {
    const q = Math.sqrt(-2 * Math.log(p));
    return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1);
  }
  if (p > high) {
    const q = Math.sqrt(-2 * Math.log(1 - p));
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1);
  }
  const q = p - 0.5;
  const r = q * q;
  return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1);
}

export function covariance(left, right) {
  const length = Math.min(left.length, right.length);
  if (length < 2) return 0;
  const leftMean = mean(left.slice(0, length));
  const rightMean = mean(right.slice(0, length));
  let total = 0;
  for (let index = 0; index < length; index += 1) total += (left[index] - leftMean) * (right[index] - rightMean);
  return total / (length - 1);
}

export function shrinkCovariance(returnRows) {
  if (!returnRows.length || !returnRows[0]?.length) return { matrix: [], intensity: 1 };
  const dimensions = returnRows[0].length;
  const columns = Array.from({ length: dimensions }, (_, column) => returnRows.map((row) => row[column]));
  const sample = Array.from({ length: dimensions }, (_, i) => Array.from({ length: dimensions }, (_, j) => covariance(columns[i], columns[j])));
  let numerator = 0;
  let denominator = 0;
  for (let i = 0; i < dimensions; i += 1) {
    for (let j = 0; j < dimensions; j += 1) {
      if (i === j) continue;
      const products = returnRows.map((row) => (row[i] - mean(columns[i])) * (row[j] - mean(columns[j])));
      numerator += variance(products) / Math.max(1, returnRows.length);
      denominator += sample[i][j] ** 2;
    }
  }
  const intensity = denominator > 0 ? clamp(numerator / denominator, 0, 1) : 1;
  const matrix = sample.map((row, i) => row.map((value, j) => (i === j ? value : value * (1 - intensity))));
  return { matrix, intensity };
}

export function portfolioVariance(weights, covarianceMatrix) {
  let total = 0;
  for (let i = 0; i < weights.length; i += 1) {
    for (let j = 0; j < weights.length; j += 1) total += weights[i] * weights[j] * covarianceMatrix[i][j];
  }
  return total;
}

export function performanceMetrics(returns, turnover = 0, costDrag = 0) {
  if (!returns.length) {
    return { observations: 0, geometricReturn: 0, annualVolatility: 0, sharpe: 0, sortino: 0, maxDrawdown: 0, cvar95: 0, hitRate: 0, turnover, costDrag, terminalWealth: 1 };
  }
  let wealth = 1;
  let peak = 1;
  let maxDrawdown = 0;
  for (const dailyReturn of returns) {
    wealth *= Math.max(1e-9, 1 + dailyReturn);
    peak = Math.max(peak, wealth);
    maxDrawdown = Math.max(maxDrawdown, 1 - wealth / peak);
  }
  const years = returns.length / TRADING_DAYS;
  const geometricReturn = years > 0 ? wealth ** (1 / years) - 1 : 0;
  const annualVolatility = standardDeviation(returns) * Math.sqrt(TRADING_DAYS);
  const annualMean = mean(returns) * TRADING_DAYS;
  const sharpe = annualVolatility > 0 ? annualMean / annualVolatility : 0;
  const downside = returns.filter((value) => value < 0);
  const downsideDeviation = Math.sqrt(mean(downside.map((value) => value ** 2))) * Math.sqrt(TRADING_DAYS);
  const sortino = downsideDeviation > 0 ? annualMean / downsideDeviation : 0;
  const threshold = quantile(returns, 0.05);
  const tail = returns.filter((value) => value <= threshold);
  return {
    observations: returns.length,
    geometricReturn,
    annualVolatility,
    sharpe,
    sortino,
    maxDrawdown,
    cvar95: Math.max(0, -mean(tail)),
    hitRate: returns.filter((value) => value > 0).length / returns.length,
    turnover,
    costDrag,
    terminalWealth: wealth,
  };
}

export function probabilisticSharpe(returns, benchmarkSharpe = 0) {
  if (returns.length < 3) return 0;
  const average = mean(returns);
  const sigma = standardDeviation(returns);
  if (sigma <= 0) return 0;
  const dailySharpe = average / sigma;
  const centered = returns.map((value) => value - average);
  const skew = mean(centered.map((value) => value ** 3)) / sigma ** 3;
  const kurtosis = mean(centered.map((value) => value ** 4)) / sigma ** 4;
  const varianceEstimate = Math.max(1e-12, (1 - skew * dailySharpe + ((kurtosis - 1) / 4) * dailySharpe ** 2) / (returns.length - 1));
  const benchmarkDaily = benchmarkSharpe / Math.sqrt(TRADING_DAYS);
  return normalCdf((dailySharpe - benchmarkDaily) / Math.sqrt(varianceEstimate));
}

export function deflatedSharpe(returns, trialCount, trialSharpeVariance) {
  if (returns.length < 3) return 0;
  const effectiveTrials = Math.max(1, Math.round(trialCount));
  const euler = 0.5772156649015329;
  const expectedMaximumZ = effectiveTrials <= 1
    ? 0
    : (1 - euler) * inverseNormal(1 - 1 / effectiveTrials) + euler * inverseNormal(1 - 1 / (effectiveTrials * Math.E));
  const hurdle = expectedMaximumZ * Math.sqrt(Math.max(1e-12, trialSharpeVariance));
  return probabilisticSharpe(returns, hurdle);
}

export function seededRandom(seed = 20260807) {
  let state = seed >>> 0;
  return () => {
    state += 0x6d2b79f5;
    let value = state;
    value = Math.imul(value ^ (value >>> 15), value | 1);
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

export function gaussian(random) {
  const first = Math.max(1e-12, random());
  const second = Math.max(1e-12, random());
  return Math.sqrt(-2 * Math.log(first)) * Math.cos(2 * Math.PI * second);
}
