import { finite, mean, normalizeWeights, sum } from "./analytics.mjs?v=0.34.0";
import { adjustedReturn } from "./factors.mjs?v=0.34.0";
import { MODEL_VERSION } from "./policy.mjs?v=0.34.0";
import { reconcilePortfolioDistributions } from "./distribution-ledger.mjs?v=0.34.0";
const clone = (value) => JSON.parse(JSON.stringify(value));
function hash(value) {
  let h = 2166136261;
  for (const c of JSON.stringify(value)) {
    h ^= c.charCodeAt(0);
    h = Math.imul(h, 16777619);
  }
  return (h >>> 0).toString(16).padStart(8, "0");
}
export function journalOrigin(
  snapshot,
  positions,
  settings,
  overrides,
  research,
  now = new Date().toISOString(),
) {
  const {
    baseline: _baseline,
    account: _account,
    ...recordedSettings
  } = settings;
  const origin = {
    created_at: now,
    price_as_of: snapshot.price_as_of,
    information_as_of: settings.informationAsOf || snapshot.price_as_of,
    snapshot_generated_at: snapshot.generated_at,
    model_version: MODEL_VERSION,
    positions: normalizeWeights(positions),
    settings: clone(recordedSettings),
    overrides: clone(overrides || {}),
    research: clone(research || {}),
    sources: snapshot.providers || [],
    inputs: snapshot.assets
      .filter((a) => positions.some((p) => p.symbol === a.symbol))
      .map((a) => ({
        symbol: a.symbol,
        price: a.price,
        price_date: a.price_date,
        history_hash: hash(
          a.history.filter((r) => r.date <= snapshot.price_as_of),
        ),
        history_start: a.history[0]?.date,
        financials: a.financials,
        analyst_estimates: a.analyst_estimates || null,
        bond_profile: a.bond_profile || null,
        dividend_per_share: a.dividend_per_share ?? null,
        distribution_calendar: a.distribution_calendar || null,
        issuer_distributions: Array.isArray(a.issuer_distributions?.records) ? {...a.issuer_distributions,
          records:a.issuer_distributions.records.filter(r=>r.ex_date>snapshot.price_as_of)} : null,
      })),
  };
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-US", {
      timeZone: "America/New_York",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(new Date(now))
      .map((r) => [r.type, r.value]),
  );
  const localDate = `${parts.year}-${parts.month}-${parts.day}`,
    minutes = Number(parts.hour) * 60 + Number(parts.minute);
  const next = new Date(snapshot.price_as_of + "T12:00:00Z");
  do {
    next.setUTCDate(next.getUTCDate() + 1);
  } while ([0, 6].includes(next.getUTCDay()));
  const nextWeekday = next.toISOString().slice(0, 10);
  // Conservative next-weekday opening: holidays may exclude a legitimate origin,
  // but a stale close never earns a prospective score after intervening sessions.
  origin.prospective =
    (localDate > snapshot.price_as_of ||
      (localDate === snapshot.price_as_of && minutes >= 16 * 60)) &&
    (localDate < nextWeekday ||
      (localDate === nextWeekday && minutes < 9 * 60 + 30)) &&
    Date.parse(snapshot.generated_at) <= Date.parse(now) &&
    origin.information_as_of <= now.slice(0, 10);
  origin.input_hash = hash(origin);
  return clone(origin);
}
export function appendForecast(journal, origin, forecast) {
  const id =
    origin.snapshot_generated_at +
    ":" +
    hash({
      cut: origin.snapshot_generated_at,
      positions: origin.positions,
      settings: origin.settings,
      overrides: origin.overrides,
      research: origin.research,
    });
  if ((journal || []).some((row) => row.id === id)) return journal;
  const targetDate = new Date(
    Date.parse(origin.price_as_of + "T12:00:00Z") +
      forecast.horizonYears * 365.25 * 86400000,
  )
    .toISOString()
    .slice(0, 10);
  const compact = {
    id,
    origin: clone(origin),
    target_date: targetDate,
    prediction: {
      mean: forecast.meanReturn,
      median: forecast.medianReturn,
      p05: forecast.p05,
      p95: forecast.p95,
      lossProbability: forecast.lossProbability,
      horizon: forecast.horizonYears,
      model: forecast.settings.model,
      seed: forecast.settings.seed,
    },
    risk_parameters: {
      covariance: clone(forecast.covariance || []),
      marketLoadings: clone(forecast.settings.marketLoadings || {}),
    },
    cashflow_policy: clone(forecast.policy || origin.settings?.mandate || null),
    attribution: clone(
      forecast.drifts.map((r) => ({
        symbol: r.symbol,
        annual: r.annual,
        low: r.low,
        high: r.high,
        source: r.source,
      })),
    ),
  };
  return [...(journal || []), compact];
}
export function evaluateJournal(journal, snapshot) {
  const lookup = new Map(snapshot.assets.map((a) => [a.symbol, a]));
  const rows = (journal || []).map((entry) => {
    const origin = entry.origin;
    if (!origin?.prospective) return { ...entry, status: "retrospective" };
    if (entry.outcome) return { ...entry, ...entry.outcome, status: "scored" };
    if (entry.target_date > snapshot.price_as_of)
      return { ...entry, status: "immature" };
    const policy = entry.cashflow_policy || origin.settings?.mandate;
    if (
      (policy?.monthlyWithdrawal || 0) > 0 ||
      (policy?.withdrawals || []).some((r) => r.amount > 0)
    )
      return { ...entry, status: "unreconciled_flows" };
    if (
      policy?.referenceCurrency && policy.referenceCurrency !== "USD"
    )
      return { ...entry, status: "missing_fx" };
    const selected = origin.positions.map((p) => lookup.get(p.symbol));
    if (selected.some((a) => !a)) return { ...entry, status: "missing" };
    const dates = selected[0].history
      .filter(
        (r) => r.date >= entry.target_date && r.date <= snapshot.price_as_of,
      )
      .map((r) => r.date);
    const maturity = dates.find((d) =>
      selected.every((a) => a.history.some((r) => r.date === d)),
    );
    const needsLedger=policy?.dividendPolicy==="cash" || (policy?.dividendWithholding||0)>0 || (policy?.cashYield||0)>0;
    const reconciliation=needsLedger && maturity
      ? reconcilePortfolioDistributions(snapshot.assets,origin.positions,origin.price_as_of,maturity,policy)
      : null;
    if(needsLedger && maturity && !reconciliation.available)
      return {...entry,status:reconciliation.code==='missing_cash_interest'?'unreconciled_cash_interest':"unreconciled_distributions",reconciliation_reason:reconciliation.reason};
    const grossReturn = reconciliation?.available ? reconciliation.return : maturity
      ? sum(
          origin.positions.map((p, i) => {
            const r = adjustedReturn(selected[i], origin.price_as_of, maturity);
            return finite(r) ? p.weight * r : NaN;
          }),
        )
      : null;
    const realized = finite(grossReturn)
      ? (1 + grossReturn) *
          (1 -
            (origin.settings.initialCost || 0) /
              (origin.settings.capital || 100000)) -
        1
      : null;
    if (!finite(realized)) return { ...entry, status: "missing" };
    const loss = realized < 0 ? 1 : 0;
    return {
      ...entry,
      status: "scored",
      maturity,
      realized,
      error: realized - entry.prediction.mean,
      covered:
        realized >= entry.prediction.p05 && realized <= entry.prediction.p95,
      brier: (entry.prediction.lossProbability - loss) ** 2,
      distribution_reconciliation:reconciliation?.available?reconciliation:null,
    };
  });
  const scored = rows.filter((r) => r.status === "scored");
  return {
    rows,
    count: scored.length,
    brier: mean(scored.map((r) => r.brier)),
    mae: mean(scored.map((r) => Math.abs(r.error))),
    coverage: scored.length
      ? scored.filter((r) => r.covered).length / scored.length
      : null,
    note: "Sólo orígenes prospectivos vencidos, sin retiros ni operaciones posteriores. Los dividendos conciliados usan fechas e importes del emisor, cierre de reinversión y retención supuesta del modelo; no son rendimiento del broker. Ventanas solapadas no son observaciones independientes. Falta de datos se conserva como no evaluable.",
  };
}

export function freezeMaturedOutcomes(journal, snapshot) {
  const results = new Map(
    evaluateJournal(journal, snapshot)
      .rows.filter((r) => r.status === "scored" && !r.outcome)
      .map((r) => [r.id, r]),
  );
  if (!results.size) return journal;
  return journal.map((entry) => {
    const r = results.get(entry.id);
    return r
      ? {
          ...entry,
          outcome: {
            maturity: r.maturity,
            realized: r.realized,
            error: r.error,
            covered: r.covered,
            brier: r.brier,
            distribution_reconciliation:r.distribution_reconciliation||null,
            observed_at: snapshot.generated_at,
          },
        }
      : entry;
  });
}
