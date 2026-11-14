/** Presentation of the published simulated fund. It never recomputes or changes weights. */
import { template } from './templates.mjs?v=0.35.0';
import { fmt, pct, money, dateLabel } from './format.mjs?v=0.35.0';

const MODEL_LABELS = { original: 'Base', no_rerating: 'Sin re-rating', margin_stress: 'Margen y crédito',
  combined: 'Combinado', low_conviction: 'Baja convicción' };
const CLASS_LABELS = { 'us-equity': 'Acciones EE. UU.', 'international-equity': 'Acciones internacionales',
  'global-equity': 'Acciones globales', 'direct-equity': 'Acción', treasury: 'Treasuries', credit: 'Crédito',
  'mixed-bond': 'Bonos mixtos', 'municipal-bond': 'Municipales', gold: 'Oro', silver: 'Plata' };

export function validFund(fund) {
  return !!fund && fund.schema_version === 1 && typeof fund.policy === 'string' &&
    Array.isArray(fund.holdings) && Number.isFinite(fund.value) && /^\d{4}-\d{2}-\d{2}$/.test(fund.as_of || '');
}

export function fundPanel(fund, market) {
  if (!validFund(fund)) return '';
  const review = fund.last_review, stale = fund.as_of !== market?.price_as_of;
  const metric = (label, value, sub, className = '') => template('metric', { label, forecastsIcon: '',
    className, value, value5: '', sub });
  const metrics = [
    metric('VALOR DEL FONDO', money(fund.value, 0),
      `${pct(fund.return_since_inception, 2, true)} desde ${dateLabel(fund.inception)} · dividendos reinvertidos`,
      fund.return_since_inception > 0 ? 'positive' : fund.return_since_inception < 0 ? 'negative' : ''),
    metric('FRENTE A 60/40', fund.benchmarks ? pct(fund.return_since_inception - fund.benchmarks.balanced_60_40, 2, true) : '—',
      fund.benchmarks ? `60/40 ${pct(fund.benchmarks.balanced_60_40, 2, true)} · SPY ${pct(fund.benchmarks.spy, 2, true)} · Letras ${pct(fund.benchmarks.tbills, 2, true)}` : 'Referencias desde el inicio',
      fund.benchmarks && fund.return_since_inception < fund.benchmarks.balanced_60_40 ? 'negative' : ''),
    metric('RENTA VARIABLE', pct(fund.equity_weight, 0), `Mandato ${pct(fund.mandate.equity[0], 0)}–${pct(fund.mandate.equity[1], 0)}`),
    metric('RETORNO MEDIANO · 1 AÑO', review?.metrics ? pct(review.metrics.median_return, 1) : '—',
      review?.metrics ? `CVaR 95% ${pct(review.metrics.cvar95, 1)} · P(pérdida) ${pct(review.metrics.loss_probability, 0)}` : 'Modelo, no pronóstico validado'),
  ].join('');
  const rows = fund.holdings.map(h => template('fund-row', { symbol: h.symbol, symbol2: h.symbol, name: h.name,
    weight: pct(h.weight, 1), shares: fmt(h.shares, 2), whole: fmt(h.whole_shares, 0), price: money(h.price, 2),
    value: money(h.value, 0), kind: CLASS_LABELS[h.class] || h.class })).join('') +
    template('fund-row', { symbol: 'CASH', symbol2: 'EFECTIVO', name: 'Liquidez sin remuneración', weight: pct(fund.cash_weight, 1),
      shares: '—', whole: '—', price: '—', value: money(fund.cash, 0), kind: 'Efectivo' });
  const decision = !review ? 'Sin revisiones todavía.'
    : review.status === 'rebalance' ? 'Cambio de cartera: la nueva composición mejoró a mantener en todos los modelos que deciden y cumplió los límites de riesgo.'
    : review.reason || 'Se mantiene la cartera vigente.';
  const m = fund.mandate;
  const rule = `Solo cambia si la cota inferior de la mejora supera ${money(m.min_benefit, 0)} o ${m.benefit_cost_ratio} veces el costo en cada modelo que decide; ` +
    `volver a una cartera abandonada en ${m.hysteresis.sessions} sesiones exige ${m.hysteresis.multiplier} veces el umbral. ` +
    `${fund.rebalances.length} cambio(s) desde el inicio.`;
  const evidence = review?.evidence?.length ? template('fund-evidence', { rows: [
    ...review.evidence.map(e => template('fund-evidence-row', { model: MODEL_LABELS[e.model] || e.model, role: 'Decide',
      gain: money(e.gain, 0), lower: money(e.lower_gain, 0), result: e.failures.length ? 'Falla: ' + e.failures.join(', ') : 'Cumple' })),
    ...(review.risk_only || []).map(e => template('fund-evidence-row', { model: MODEL_LABELS[e.model] || e.model,
      role: 'Solo riesgo', gain: '—', lower: '—', result: e.failures.length ? 'Falla: ' + e.failures.join(', ') : 'Cumple límites' })),
  ].join('') }) : '';
  const orders = review?.orders?.length ? template('fund-orders', { date: dateLabel(review.date), rows: review.orders.map(o =>
    template('fund-order-row', { symbol: o.symbol, side: o.trade_shares >= 0 ? 'Comprar' : 'Vender',
      shares: fmt(Math.abs(o.trade_shares), 2), whole: fmt(Math.abs(o.trade_whole_shares), 0), price: money(o.price, 2) })).join('') }) : '';
  return template('fund-panel', {
    policy: fund.policy, statusLabel: review?.status === 'rebalance' ? 'CAMBIO REGISTRADO' : 'CARTERA VIGENTE',
    notice: stale ? template('fund-notice', { message: `El fondo se revisó con el corte del ${dateLabel(fund.as_of)}; el mercado cargado es del ${dateLabel(market?.price_as_of)}. La próxima revisión automática lo actualizará.` }) : '',
    source: `Solo ETF que cotizan en EE. UU. · revisión tras cada actualización de mercado · precios ${dateLabel(fund.as_of)}`,
    metrics, reviewDate: review ? dateLabel(review.date) : '—', decision, rule, rows, evidence, orders,
    footnote: 'Simulación de investigación con la política fija fondo-v1. Las acciones enteras sirven para simuladores sin fracciones. El retorno esperado y el riesgo son del modelo; la capacidad predictiva no está acreditada.',
  });
}
