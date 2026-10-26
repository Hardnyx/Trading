import { template } from "./ui/templates.mjs?v=0.8.2";
import { finite, wealth } from "./analytics.mjs?v=0.8.2";

export const COLORS = [
  "var(--chart-accent)",
  "var(--chart-secondary)",
  "var(--chart-neutral)",
  "var(--chart-fourth)",
  "var(--chart-accent)",
  "var(--chart-secondary)",
  "var(--chart-neutral)",
  "var(--chart-fourth)",
];
const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const number = (x, n = 1) =>
  finite(x)
    ? x.toLocaleString("en-US", {
        maximumFractionDigits: n,
        minimumFractionDigits: n,
      })
    : "—";

export function sparkline(
  values,
  color = "var(--chart-primary)",
  width = 110,
  height = 28,
) {
  if (values.length < 2) return "";
  const min = Math.min(...values),
    max = Math.max(...values),
    span = max - min || 1;
  const points = values
    .map(
      (v, i) =>
        `${((i * width) / (values.length - 1)).toFixed(1)},${(height - 3 - ((v - min) / span) * (height - 6)).toFixed(1)}`,
    )
    .join(" ");
  return template("chart-sparkline", {
    width: width,
    height: height,
    points: points,
    color: color,
  });
}

export function lineChart(
  series,
  dates,
  {
    height = 255,
    percent = false,
    label = "Evolución de la cartera",
    area = true,
  } = {},
) {
  if (!series.length || !dates.length) return template("chart-line-chart-7");
  const width = 920,
    pad = { top: 22, right: 54, bottom: 31, left: 13 };
  const values = series.flatMap((s) => s.values).filter(finite);
  if (!values.length) return "";
  let min = Math.min(...values),
    max = Math.max(...values);
  const span = max - min || 1;
  min -= span * 0.12;
  max += span * 0.12;
  const pw = width - pad.left - pad.right,
    ph = height - pad.top - pad.bottom;
  const x = (i) => pad.left + (i / Math.max(1, dates.length - 1)) * pw;
  const y = (v) => pad.top + ((max - v) / (max - min)) * ph;
  const grid = Array.from({ length: 5 }, (_, i) => {
    const value = min + ((max - min) * i) / 4;
    return template("chart-line-chart-6", {
      left: pad.left,
      value2: width - pad.right,
      y: y(value),
      y4: y(value),
      value5: width - pad.right + 10,
      value6: y(value) + 4,
      number: number(percent ? value * 100 : value, percent ? 0 : 1),
      value8: percent ? "%" : "",
    });
  }).join("");
  const ticks = [
    0,
    Math.round((dates.length - 1) / 4),
    Math.round((dates.length - 1) / 2),
    Math.round(((dates.length - 1) * 3) / 4),
    dates.length - 1,
  ];
  const labels = ticks
    .map((i, t) =>
      template("chart-line-chart-5", {
        x: x(i),
        value2: height - 7,
        value3: t === 0 ? "start" : t === 4 ? "end" : "middle",
        slice: dates[i]?.slice(2),
      }),
    )
    .join("");
  const paths = series
    .map((s, i) => {
      const d = s.values
        .map((v, t) => `${t ? "L" : "M"}${x(t).toFixed(2)},${y(v).toFixed(2)}`)
        .join(" ");
      const fill =
        i === 0 && area
          ? template("chart-line-chart-4", {
              d: d,
              x: x(s.values.length - 1),
              value3: height - pad.bottom,
              x4: x(0),
              value5: height - pad.bottom,
            })
          : "";
      return template("chart-line-chart-3", {
        fill: fill,
        d: d,
        color: s.color,
        value4: i === 0 ? 2 : 1.4,
        value5: s.dashed ? 'stroke-dasharray="5 4"' : "",
        x: x(s.values.length - 1),
        y: y(s.values.at(-1)),
        color8: s.color,
      });
    })
    .join("");
  const hover = dates
    .map((date, i) =>
      template("chart-line-chart-2", {
        value1: x(i) - pw / dates.length / 2,
        top: pad.top,
        max: Math.max(1, pw / dates.length),
        ph: ph,
        date: date,
        items: series
          .map(
            (s) =>
              ` · ${esc(s.name)}: ${number(percent ? s.values[i] * 100 : s.values[i], 2)}${percent ? "%" : ""}`,
          )
          .join(""),
      }),
    )
    .join("");
  return template("chart-line-chart", {
    width: width,
    height: height,
    label: label,
    color: series[0].color,
    color5: series[0].color,
    grid: grid,
    labels: labels,
    paths: paths,
    hover: hover,
  });
}

export function portfolioChart(
  analysis,
  { height = 250, drawdown = false } = {},
) {
  if (!analysis) return template("chart-portfolio-chart");
  const { dates, returns, benchmarkReturns } = analysis;
  const displayDates = [dates[0], ...dates];
  if (drawdown) {
    let peak = 100;
    const values = wealth(returns).map((v) => {
      peak = Math.max(peak, v);
      return v / peak - 1;
    });
    return lineChart(
      [{ name: "Drawdown", values, color: "var(--chart-drawdown)" }],
      displayDates,
      { height, percent: true, label: "Caída desde máximos de la cartera" },
    );
  }
  return lineChart(
    [
      {
        name: "Cartera",
        values: wealth(returns),
        color: "var(--chart-primary)",
      },
      ...(benchmarkReturns.length
        ? [
            {
              name: "SPY",
              values: wealth(benchmarkReturns),
              color: "var(--chart-benchmark)",
              dashed: true,
            },
          ]
        : []),
    ],
    displayDates,
    { height },
  );
}

export function heatmap(analysis) {
  if (!analysis) return template("chart-heatmap-6");
  const symbols = analysis.weights.map((p) => p.symbol);
  const header = template("chart-heatmap-4", {
    items: symbols
      .map((s) => template("chart-heatmap-5", { s: s, s2: s }))
      .join(""),
  });
  const rows = symbols
    .map((s, i) =>
      template("chart-heatmap-2", {
        s: s,
        s2: s,
        items: analysis.matrix[i]
          .map((v, j) => {
            const tone = !finite(v)
              ? "heat-unavailable"
              : v >= 0
                ? "heat-positive"
                : "heat-negative";
            const opacity = !finite(v)
              ? 1
              : v >= 0
                ? i === j
                  ? 0.78
                  : 0.06 + Math.abs(v) * 0.55
                : 0.08 + Math.abs(v) * 0.55;
            return template("chart-heatmap-3", {
              tone: tone,
              value2: i === j ? " diagonal" : "",
              opacity: opacity,
              s: s,
              j: symbols[j],
              number: number(v, 3),
              number7: number(v, 2),
            });
          })
          .join(""),
      }),
    )
    .join("");
  return template("chart-heatmap", {
    length: symbols.length,
    header: header,
    rows: rows,
  });
}

export function scatter(points, portfolio) {
  const valid = points.filter((p) => finite(p.x) && finite(p.y));
  if (!valid.length) return "";
  const all = portfolio ? [...valid, portfolio] : valid;
  const width = 650,
    height = 310,
    pad = { l: 52, r: 28, t: 25, b: 47 };
  const maxX = Math.max(0.2, ...all.map((p) => p.x)) * 1.16;
  const minY = Math.min(0, ...all.map((p) => p.y)) - 0.03,
    maxY = Math.max(0.1, ...all.map((p) => p.y)) + 0.08;
  const x = (v) => pad.l + (v / maxX) * (width - pad.l - pad.r),
    y = (v) => pad.t + ((maxY - v) / (maxY - minY)) * (height - pad.t - pad.b);
  const grids = Array.from({ length: 5 }, (_, i) => {
    const xv = (maxX * i) / 4,
      yv = minY + ((maxY - minY) * i) / 4;
    return template("chart-scatter-4", {
      x: x(xv),
      x2: x(xv),
      t: pad.t,
      value4: height - pad.b,
      l: pad.l,
      value6: width - pad.r,
      y: y(yv),
      y8: y(yv),
      x9: x(xv),
      value10: height - 26,
      number: number(xv * 100, 0),
      value12: pad.l - 9,
      value13: y(yv) + 4,
      number14: number(yv * 100, 0),
    });
  }).join("");
  return template("chart-scatter", {
    width: width,
    height: height,
    grids: grids,
    items: valid
      .map((p, i) =>
        template("chart-scatter-2", {
          x: x(p.x),
          y: y(p.y),
          value3: COLORS[i % COLORS.length],
          value4: x(p.x) + 8,
          value5: y(p.y) + 3,
          symbol: p.symbol,
          symbol7: p.symbol,
          number: number(p.x * 100),
          number9: number(p.y * 100),
        }),
      )
      .join(""),
    value5: portfolio
      ? template("chart-scatter-3", {
          x: x(portfolio.x),
          y: y(portfolio.y),
          x3: x(portfolio.x),
          value4: y(portfolio.y) + 4,
          value5: x(portfolio.x) + 15,
          value6: y(portfolio.y) - 10,
        })
      : "",
    value6: width / 2,
    value7: height - 3,
  });
}

export function forecastCone(forecast, height = 270) {
  if (!forecast) return template("chart-forecast-cone-5");
  const width = 920,
    pad = { l: 14, r: 60, t: 22, b: 31 },
    bands = forecast.bands;
  const lo = Math.min(90, ...bands.map((b) => b.p05)) * 0.96,
    hi = Math.max(...bands.map((b) => b.p95)) * 1.035;
  const x = (i) => pad.l + (i / (bands.length - 1)) * (width - pad.l - pad.r);
  const y = (v) => pad.t + ((hi - v) / (hi - lo)) * (height - pad.t - pad.b);
  const path = (key) =>
    bands
      .map(
        (b, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(b[key]).toFixed(1)}`,
      )
      .join(" ");
  const area = (upper, lower) =>
    `${path(upper)} ${[...bands]
      .reverse()
      .map(
        (b, i) =>
          `L${x(bands.length - 1 - i).toFixed(1)},${y(b[lower]).toFixed(1)}`,
      )
      .join(" ")} Z`;
  const grid = Array.from({ length: 5 }, (_, i) => {
    const value = lo + ((hi - lo) * i) / 4;
    return template("chart-forecast-cone-4", {
      l: pad.l,
      value2: width - pad.r,
      y: y(value),
      y4: y(value),
      value5: width - pad.r + 11,
      value6: y(value) + 4,
      number: number(value, 0),
    });
  }).join("");
  const ticks = [0, 1, 2, 3, 4]
    .map((i) => {
      const index = Math.round(((bands.length - 1) * i) / 4),
        months = bands[index].year * 12;
      return template("chart-forecast-cone-3", {
        x: x(index),
        value2: height - 7,
        value3: i === 0 ? "start" : i === 4 ? "end" : "middle",
        value4:
          i === 0 ? "HOY" : "+" + number(months, months % 1 ? 1 : 0) + "M",
      });
    })
    .join("");
  return template("chart-forecast-cone", {
    width: width,
    height: height,
    grid: grid,
    area: area("p95", "p05"),
    area5: area("p75", "p25"),
    l: pad.l,
    value7: width - pad.r,
    y: y(100),
    y9: y(100),
    path: path("p95"),
    path11: path("p05"),
    path12: path("p50"),
    x: x(bands.length - 1),
    y14: y(bands.at(-1).p50),
    ticks: ticks,
    items: bands
      .map((b, i) =>
        template("chart-forecast-cone-2", {
          value1: x(i) - 5,
          t: pad.t,
          value3: height - pad.t - pad.b,
          number: number(b.year * 12, 1),
          number5: number(b.p05),
          number6: number(b.p50),
          number7: number(b.p95),
        }),
      )
      .join(""),
  });
}

export function histogram(forecast) {
  if (!forecast) return template("chart-histogram-4");
  const bins = forecast.histogram,
    width = 650,
    height = 225,
    left = 16,
    right = 20,
    bottom = 35,
    top = 17;
  const max = Math.max(...bins.map((b) => b.count)),
    bw = (width - left - right) / bins.length;
  const bars = bins
    .map((b, i) => {
      const h = (b.count / max) * (height - top - bottom),
        color =
          (b.low + b.high) / 2 < 0
            ? "var(--histogram-negative)"
            : "var(--histogram-positive)";
      return template("chart-histogram-3", {
        value1: left + i * bw + 1,
        value2: height - bottom - h,
        value3: bw - 2,
        h: h,
        color: color,
        number: number(b.low * 100, 1),
        number7: number(b.high * 100, 1),
        count: b.count,
      });
    })
    .join("");
  const ticks = [0, 6, 12, 18, 25]
    .map((i) =>
      template("chart-histogram-2", {
        value1: left + (i + 0.5) * bw,
        value2: height - 13,
        number: number((bins[i].low + bins[i].high) * 50, 0),
      }),
    )
    .join("");
  return template("chart-histogram", {
    width: width,
    height: height,
    bars: bars,
    ticks: ticks,
  });
}
