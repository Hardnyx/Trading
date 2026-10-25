import { finite, wealth } from './analytics.mjs';

export const COLORS = ['#ff9f00', '#79b8e3', '#c6c6c6', '#e0b357', '#ff9f00', '#79b8e3', '#c6c6c6', '#e0b357'];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const number = (x, n = 1) => finite(x) ? x.toLocaleString('en-US', { maximumFractionDigits: n, minimumFractionDigits: n }) : '—';

export function sparkline(values, color = '#ff982b', width = 110, height = 28) {
  if (values.length < 2) return '';
  const min = Math.min(...values), max = Math.max(...values), span = max - min || 1;
  const points = values.map((v, i) => `${(i * width / (values.length - 1)).toFixed(1)},${(height - 3 - (v - min) / span * (height - 6)).toFixed(1)}`).join(' ');
  return `<svg class="sparkline" viewBox="0 0 ${width} ${height}" aria-hidden="true"><polyline points="${points}" fill="none" stroke="${color}" stroke-width="1.35" vector-effect="non-scaling-stroke"/></svg>`;
}

export function lineChart(series, dates, { height = 255, percent = false, label = 'Evolución de la cartera', area = true } = {}) {
  if (!series.length || !dates.length) return '<div class="empty-chart">Agrega activos para visualizar la cartera.</div>';
  const width = 920, pad = { top: 22, right: 54, bottom: 31, left: 13 };
  const values = series.flatMap(s => s.values).filter(finite);
  if (!values.length) return '';
  let min = Math.min(...values), max = Math.max(...values);
  const span = max - min || 1;
  min -= span * 0.12; max += span * 0.12;
  const pw = width - pad.left - pad.right, ph = height - pad.top - pad.bottom;
  const x = i => pad.left + i / Math.max(1, dates.length - 1) * pw;
  const y = v => pad.top + (max - v) / (max - min) * ph;
  const grid = Array.from({ length: 5 }, (_, i) => {
    const value = min + (max - min) * i / 4;
    return `<line x1="${pad.left}" x2="${width - pad.right}" y1="${y(value)}" y2="${y(value)}" class="chart-grid"/><text x="${width - pad.right + 10}" y="${y(value) + 4}" class="axis-label">${number(percent ? value * 100 : value, percent ? 0 : 1)}${percent ? '%' : ''}</text>`;
  }).join('');
  const ticks = [0, Math.round((dates.length - 1) / 4), Math.round((dates.length - 1) / 2), Math.round((dates.length - 1) * 3 / 4), dates.length - 1];
  const labels = ticks.map((i, t) => `<text x="${x(i)}" y="${height - 7}" class="axis-label" text-anchor="${t === 0 ? 'start' : t === 4 ? 'end' : 'middle'}">${esc(dates[i]?.slice(2))}</text>`).join('');
  const paths = series.map((s, i) => {
    const d = s.values.map((v, t) => `${t ? 'L' : 'M'}${x(t).toFixed(2)},${y(v).toFixed(2)}`).join(' ');
    const fill = i === 0 && area ? `<path d="${d} L${x(s.values.length - 1)},${height - pad.bottom} L${x(0)},${height - pad.bottom} Z" fill="url(#chart-fill)"/>` : '';
    return `${fill}<path d="${d}" fill="none" stroke="${s.color}" stroke-width="${i === 0 ? 2 : 1.4}" ${s.dashed ? 'stroke-dasharray="5 4"' : ''} vector-effect="non-scaling-stroke"/><circle cx="${x(s.values.length - 1)}" cy="${y(s.values.at(-1))}" r="3" fill="${s.color}"/>`;
  }).join('');
  const hover = dates.map((date, i) => `<rect x="${x(i) - pw / dates.length / 2}" y="${pad.top}" width="${Math.max(1, pw / dates.length)}" height="${ph}" fill="transparent"><title>${esc(date)}${series.map(s => ` · ${esc(s.name)}: ${number(percent ? s.values[i] * 100 : s.values[i], 2)}${percent ? '%' : ''}`).join('')}</title></rect>`).join('');
  return `<svg class="line-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(label)}"><defs><linearGradient id="chart-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="${series[0].color}" stop-opacity=".13"/><stop offset="100%" stop-color="${series[0].color}" stop-opacity="0"/></linearGradient></defs>${grid}${labels}${paths}${hover}</svg>`;
}

export function portfolioChart(analysis, { height = 250, drawdown = false } = {}) {
  if (!analysis) return '<div class="empty-chart">Selecciona al menos un activo con historia suficiente.</div>';
  const { dates, returns, benchmarkReturns } = analysis;
  const displayDates = [dates[0], ...dates];
  if (drawdown) {
    let peak = 100;
    const values = wealth(returns).map(v => { peak = Math.max(peak, v); return v / peak - 1; });
    return lineChart([{ name: 'Drawdown', values, color: '#ef7076' }], displayDates, { height, percent: true, label: 'Caída desde máximos de la cartera' });
  }
  return lineChart([
    { name: 'Cartera', values: wealth(returns), color: '#ff982b' },
    ...(benchmarkReturns.length ? [{ name: 'SPY', values: wealth(benchmarkReturns), color: '#648da7', dashed: true }] : []),
  ], displayDates, { height });
}

export function donut(weights, assets, size = 180) {
  const lookup = new Map(assets.map(a => [a.symbol, a]));
  const radius = 63, length = 2 * Math.PI * radius;
  let offset = 0;
  const arcs = weights.map((p, i) => {
    const arc = `<circle cx="90" cy="90" r="${radius}" fill="none" stroke="${COLORS[i % COLORS.length]}" stroke-width="16" stroke-dasharray="${Math.max(0, p.weight * length - 2)} ${length}" stroke-dashoffset="${-offset}" transform="rotate(-90 90 90)"><title>${esc(p.symbol)} · ${number(p.weight * 100)} %</title></circle>`;
    offset += p.weight * length;
    return arc;
  }).join('');
  return `<svg class="donut" viewBox="0 0 180 180" width="${size}" height="${size}" role="img" aria-label="Distribución por activo"><circle cx="90" cy="90" r="63" fill="none" stroke="#1b242c" stroke-width="16"/>${arcs}<text x="90" y="88" text-anchor="middle" class="donut-number">${weights.length.toString().padStart(2, '0')}</text><text x="90" y="107" text-anchor="middle" class="donut-label">ACTIVOS</text></svg>`;
}

export function heatmap(analysis) {
  if (!analysis) return '<div class="empty-chart">La matriz aparecerá al agregar activos.</div>';
  const symbols = analysis.weights.map(p => p.symbol);
  const header = `<div class="heat-label heat-corner">ρ</div>${symbols.map(s => `<button class="heat-label" data-detail="${esc(s)}">${esc(s)}</button>`).join('')}`;
  const rows = symbols.map((s, i) => `<button class="heat-label" data-detail="${esc(s)}">${esc(s)}</button>${analysis.matrix[i].map((v, j) => {
    const color = !finite(v) ? '#18202a' : v >= 0 ? `rgba(238,145,53,${i === j ? '.78' : (.06 + Math.abs(v) * .55).toFixed(2)})` : `rgba(59,165,205,${(.08 + Math.abs(v) * .55).toFixed(2)})`;
    return `<div class="heat-cell${i === j ? ' diagonal' : ''}" style="background:${color}" title="${esc(s)} / ${esc(symbols[j])}: ${number(v, 3)}">${number(v, 2)}</div>`;
  }).join('')}`).join('');
  return `<div class="heatmap" style="grid-template-columns:54px repeat(${symbols.length},minmax(40px,1fr))">${header}${rows}</div>`;
}

export function scatter(points, portfolio) {
  const valid = points.filter(p => finite(p.x) && finite(p.y));
  if (!valid.length) return '';
  const all = portfolio ? [...valid, portfolio] : valid;
  const width = 650, height = 310, pad = { l: 52, r: 28, t: 25, b: 47 };
  const maxX = Math.max(0.2, ...all.map(p => p.x)) * 1.16;
  const minY = Math.min(0, ...all.map(p => p.y)) - .03, maxY = Math.max(.1, ...all.map(p => p.y)) + .08;
  const x = v => pad.l + v / maxX * (width - pad.l - pad.r), y = v => pad.t + (maxY - v) / (maxY - minY) * (height - pad.t - pad.b);
  const grids = Array.from({ length: 5 }, (_, i) => {
    const xv = maxX * i / 4, yv = minY + (maxY - minY) * i / 4;
    return `<line x1="${x(xv)}" x2="${x(xv)}" y1="${pad.t}" y2="${height - pad.b}" class="chart-grid"/><line x1="${pad.l}" x2="${width - pad.r}" y1="${y(yv)}" y2="${y(yv)}" class="chart-grid"/><text x="${x(xv)}" y="${height - 26}" text-anchor="middle" class="axis-label">${number(xv * 100, 0)}%</text><text x="${pad.l - 9}" y="${y(yv) + 4}" text-anchor="end" class="axis-label">${number(yv * 100, 0)}%</text>`;
  }).join('');
  return `<svg class="scatter-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Volatilidad y retorno histórico anualizados">${grids}${valid.map((p, i) => `<g><circle cx="${x(p.x)}" cy="${y(p.y)}" r="5" fill="${COLORS[i % COLORS.length]}" opacity=".85"/><text x="${x(p.x) + 8}" y="${y(p.y) + 3}" class="scatter-label">${esc(p.symbol)}</text><title>${esc(p.symbol)} · Vol ${number(p.x * 100)} % · Ret ${number(p.y * 100)} %</title></g>`).join('')}${portfolio ? `<circle cx="${x(portfolio.x)}" cy="${y(portfolio.y)}" r="10" fill="#11171c" stroke="#ff982b" stroke-width="2"/><text x="${x(portfolio.x)}" y="${y(portfolio.y) + 4}" text-anchor="middle" fill="#ff982b" font-size="10" font-weight="bold">P</text><text x="${x(portfolio.x) + 15}" y="${y(portfolio.y) - 10}" fill="#ff982b" font-size="10">CARTERA</text>` : ''}<text x="${width / 2}" y="${height - 3}" text-anchor="middle" class="axis-label">VOLATILIDAD ANUALIZADA →</text></svg>`;
}

export function forecastCone(forecast, height = 270) {
  if (!forecast) return '<div class="empty-chart"><span class="orange">Calculando distribución de resultados…</span></div>';
  const width = 920, pad = { l: 14, r: 60, t: 22, b: 31 }, bands = forecast.bands;
  const lo = Math.min(90, ...bands.map(b => b.p05)) * .96, hi = Math.max(...bands.map(b => b.p95)) * 1.035;
  const x = i => pad.l + i / (bands.length - 1) * (width - pad.l - pad.r);
  const y = v => pad.t + (hi - v) / (hi - lo) * (height - pad.t - pad.b);
  const path = key => bands.map((b, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(b[key]).toFixed(1)}`).join(' ');
  const area = (upper, lower) => `${path(upper)} ${[...bands].reverse().map((b, i) => `L${x(bands.length - 1 - i).toFixed(1)},${y(b[lower]).toFixed(1)}`).join(' ')} Z`;
  const grid = Array.from({ length: 5 }, (_, i) => {
    const value = lo + (hi - lo) * i / 4;
    return `<line x1="${pad.l}" x2="${width - pad.r}" y1="${y(value)}" y2="${y(value)}" class="chart-grid"/><text x="${width - pad.r + 11}" y="${y(value) + 4}" class="axis-label">${number(value, 0)}</text>`;
  }).join('');
  const ticks = [0, 1, 2, 3, 4].map(i => {
    const index = Math.round((bands.length - 1) * i / 4), months = bands[index].year * 12;
    return `<text x="${x(index)}" y="${height - 7}" class="axis-label" text-anchor="${i === 0 ? 'start' : i === 4 ? 'end' : 'middle'}">${i === 0 ? 'HOY' : '+' + number(months, months % 1 ? 1 : 0) + 'M'}</text>`;
  }).join('');
  return `<svg class="line-chart forecast-cone" viewBox="0 0 ${width} ${height}" role="img" aria-label="Proyección probabilística: mediana y bandas entre percentiles 5 y 95, base 100">${grid}<path d="${area('p95','p05')}" fill="#ff982b" opacity=".07"/><path d="${area('p75','p25')}" fill="#ff982b" opacity=".15"/><line x1="${pad.l}" x2="${width-pad.r}" y1="${y(100)}" y2="${y(100)}" stroke="#63788b" stroke-dasharray="4 5" stroke-width=".7"/><path d="${path('p95')}" fill="none" stroke="#986431" stroke-width=".7" stroke-dasharray="3 4"/><path d="${path('p05')}" fill="none" stroke="#986431" stroke-width=".7" stroke-dasharray="3 4"/><path d="${path('p50')}" fill="none" stroke="#ff982b" stroke-width="2.2"/><circle cx="${x(bands.length-1)}" cy="${y(bands.at(-1).p50)}" r="3.5" fill="#ff982b"/>${ticks}${bands.map((b,i)=>`<rect x="${x(i)-5}" width="10" y="${pad.t}" height="${height-pad.t-pad.b}" fill="transparent"><title>Mes ${number(b.year*12,1)} · P05 ${number(b.p05)} · P50 ${number(b.p50)} · P95 ${number(b.p95)}</title></rect>`).join('')}</svg>`;
}

export function histogram(forecast) {
  if (!forecast) return '<div class="empty-chart">Calculando…</div>';
  const bins = forecast.histogram, width = 650, height = 225, left = 16, right = 20, bottom = 35, top = 17;
  const max = Math.max(...bins.map(b => b.count)), bw = (width-left-right)/bins.length;
  const bars = bins.map((b,i) => {
    const h = b.count/max*(height-top-bottom), color = (b.low+b.high)/2 < 0 ? '#bc5d64' : '#d38b3c';
    return `<rect x="${left+i*bw+1}" y="${height-bottom-h}" width="${bw-2}" height="${h}" fill="${color}"><title>${number(b.low*100,1)}% a ${number(b.high*100,1)}% · ${b.count} simulaciones</title></rect>`;
  }).join('');
  const ticks = [0,6,12,18,25].map(i=>`<text x="${left+(i+.5)*bw}" y="${height-13}" text-anchor="middle" class="axis-label">${number((bins[i].low+bins[i].high)*50,0)}%</text>`).join('');
  return `<svg class="histogram" viewBox="0 0 ${width} ${height}" role="img" aria-label="Distribución de retornos terminales de Monte Carlo">${bars}${ticks}</svg>`;
}
