/** Presentation of the published simulated fund and a local what-if mix. Never changes the fund. */
import { template } from './templates.mjs?v=0.35.0';
import { fmt, pct, money, dateLabel } from './format.mjs?v=0.35.0';
import { mixWeights, ordersFor } from '../strategic-fund.mjs?v=0.35.0';

export function validFund(fund) {
  return !!fund && fund.schema_version === 2 && typeof fund.policy === 'string' && Array.isArray(fund.holdings) &&
    Number.isFinite(fund.value) && /^\d{4}-\d{2}-\d{2}$/.test(fund.as_of || '') && !!fund.mix && !!fund.prices;
}

/** Normalized personal mix; falls back to the registered mix. */
export function personalMix(fund, saved) {
  const base = { ...fund.mix, capital: fund.initial_capital };
  const pick = (key, lo, hi) => Number.isFinite(saved?.[key]) && saved[key] >= lo && saved[key] <= hi ? saved[key] : base[key];
  return { equity: pick('equity', 0, 1), usShare: pick('usShare', 0, 1), cash: pick('cash', 0, .5),
    capital: pick('capital', 1000, 1e8) };
}

export function mixResult(fund, mix) {
  const policy = { instruments: fund.instruments }, target = mixWeights(mix, policy);
  const plan = ordersFor(fund.prices, [], mix.capital, target);
  const rows = plan.orders.map(o => template('fund-mix-row', { symbol: `${o.symbol} · ${fund.names?.[o.symbol] || ''}`,
    weight: pct(o.target_weight, 1), whole: fmt(o.target_whole_shares, 0),
    amount: money(o.target_whole_shares * o.price, 0), price: money(o.price, 2) })).join('') +
    template('fund-mix-row', { symbol: 'Efectivo', weight: pct(target.find(t => t.symbol === 'CASH')?.weight || 0, 1),
      whole: '—', amount: money(plan.whole_cash, 0), price: '—' });
  const equity = Math.min(1, mix.equity), outside = equity < .6 || equity > .9;
  return template('fund-mix-result', { rows, summary: `Acciones ${pct(equity, 0)} · bonos ${pct(Math.max(0, 1 - equity - Math.min(mix.cash, 1 - equity)), 0)} · ` +
    `efectivo tras redondeo ${money(plan.whole_cash, 0)} · precios ${dateLabel(fund.as_of)}` +
    (outside ? ' · fuera del mandato registrado de 60–90 % en acciones' : '') });
}

export function fundPanel(fund, market, saved = null) {
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
    metric('RENTA VARIABLE', pct(fund.equity_weight, 0), `Objetivo ${pct(fund.mix.equity, 0)} · mandato 60%–90%`),
    metric('DESVIACIÓN MÁXIMA', review?.drift != null ? `${fmt(review.drift * 100, 1)} pp` : '—',
      `Rebalanceo si supera ${fmt(fund.threshold * 100, 0)} pp · caída desde máximo ${pct(fund.drawdown, 1)}`),
  ].join('');
  const rows = fund.holdings.map(h => template('fund-row', { symbol: h.symbol, symbol2: h.symbol, name: h.name,
    weight: pct(h.weight, 1), target: pct(h.target_weight, 1), shares: fmt(h.shares, 2), whole: fmt(h.whole_shares, 0),
    price: money(h.price, 2), value: money(h.value, 0) })).join('') +
    template('fund-row', { symbol: 'CASH', symbol2: 'EFECTIVO', name: 'Liquidez sin remuneración', weight: pct(fund.cash_weight, 1),
      target: pct(fund.target.find(t => t.symbol === 'CASH')?.weight || 0, 1), shares: '—', whole: '—', price: '—', value: money(fund.cash, 0) });
  const orders = review?.orders?.length ? template('fund-orders', { date: dateLabel(review.date), rows: review.orders.map(o =>
    template('fund-order-row', { symbol: o.symbol, side: o.trade_shares >= 0 ? 'Comprar' : 'Vender',
      shares: fmt(Math.abs(o.trade_shares), 2), whole: fmt(Math.abs(o.trade_whole_shares), 0), price: money(o.price, 2) })).join('') }) : '';
  const mix = personalMix(fund, saved);
  const mixer = template('fund-mixer', { equity: pct(mix.equity, 0), equityValue: Math.round(mix.equity * 100),
    us: pct(mix.usShare, 0), usValue: Math.round(mix.usShare * 100), cash: pct(mix.cash, 0), cashValue: Math.round(mix.cash * 100),
    capital: Math.round(mix.capital), result: mixResult(fund, mix) });
  return template('fund-panel', {
    policy: fund.policy, statusLabel: review?.status === 'rebalance' ? 'REBALANCEO REGISTRADO' : 'CARTERA VIGENTE',
    notice: stale ? template('fund-notice', { message: `El fondo se revisó con el corte del ${dateLabel(fund.as_of)}; el mercado cargado es del ${dateLabel(market?.price_as_of)}. La próxima revisión automática lo actualizará.` }) : '',
    source: `Pesos registrados: ${fund.target.map(t => `${t.symbol === 'CASH' ? 'efectivo' : t.symbol} ${pct(t.weight, 0)}`).join(' · ')} · precios ${dateLabel(fund.as_of)}`,
    metrics, reviewDate: review ? dateLabel(review.date) : '—', decision: review?.reason || 'Sin revisiones todavía.',
    rule: `Solo opera si algún componente se aparta más de ${fmt(fund.threshold * 100, 0)} pp de su objetivo; entonces vuelve a los pesos registrados. ${fund.rebalances.length} operación(es) desde el inicio.`,
    evidence: 'Mueven dinero solo el mandato, la diversificación de mercado y el rebalanceo. Las apuestas del motor (valoración, duración, momento de riesgo, acciones individuales) están apagadas hasta que una prueba registrada las respalde.',
    rows, orders, mixer,
    footnote: (fund.archived?.length ? `Archivado: ${fund.archived.map(a => `${a.policy} (${a.reason})`).join(' ')} ` : '') +
      'Simulación de investigación; un rendimiento pasado o esperado no garantiza resultados.',
  });
}
