import { finite } from "../analytics.mjs?v=0.5.3";

export const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
export const url = (s) => (/^https:\/\//.test(s || "") ? s : "#");
export const fmt = (v, n = 2) =>
  finite(v)
    ? v.toLocaleString("en-US", {
        minimumFractionDigits: n,
        maximumFractionDigits: n,
      })
    : "—";
export const pct = (v, n = 1, signed = false) =>
  finite(v) ? `${signed && v > 0 ? "+" : ""}${fmt(v * 100, n)}%` : "—";
export const money = (v, n = 2) => (finite(v) ? "$" + fmt(v, n) : "—");
export const compact = (v) =>
  !finite(v)
    ? "—"
    : Math.abs(v) >= 1e12
      ? "$" + fmt(v / 1e12, 2) + " T"
      : Math.abs(v) >= 1e9
        ? "$" + fmt(v / 1e9, 2) + " B"
        : "$" + fmt(v / 1e6, 1) + " M";
export const color = (x) =>
  finite(x) ? (x >= 0 ? "positive" : "negative") : "muted";
export const dateLabel = (d) =>
  d && /^\d{4}-\d{2}-\d{2}/.test(d)
    ? new Date(d.includes("T") ? d : d.slice(0, 10) + "T12:00:00Z")
        .toLocaleDateString("es-PE", {
          day: "2-digit",
          month: "short",
          year: "numeric",
          timeZone: d.includes("T") ? "America/Lima" : "UTC",
        })
        .replaceAll(".", "")
        .toUpperCase()
    : "—";
