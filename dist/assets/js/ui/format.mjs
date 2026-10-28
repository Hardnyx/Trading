import { finite } from "../analytics.mjs?v=0.30.0";

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
          timeZone: d.includes("T") ? localTimeZone() : "UTC",
        })
        .replaceAll(".", "")
        .toUpperCase()
    : "—";

// The browser exposes its configured time zone without geolocation permission.
export function localTimeZone() {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'; }
  catch { return 'UTC'; }
}
export function timestampLabel(value, zone = localTimeZone()) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value)) return '—';
  const instant = new Date(value);
  if (!Number.isFinite(instant.getTime())) return '—';
  try { new Intl.DateTimeFormat('es-PE', {timeZone: zone}); } catch { zone = 'UTC'; }
  const day = new Intl.DateTimeFormat('es-PE', {timeZone: zone, day:'2-digit',month:'short',year:'numeric'})
    .format(instant).replaceAll('.', '').toUpperCase();
  const clock = new Intl.DateTimeFormat('es-PE', {timeZone: zone,
    hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23',timeZoneName:'shortOffset'});
  const parts = clock.formatToParts(instant);
  const pick = type => parts.find(p=>p.type===type)?.value;
  const offset = pick('timeZoneName').replace('GMT','UTC').replace('-', '−');
  const label = zone==='UTC' ? 'UTC' : zone+' ('+offset+')';
  return day+' '+pick('hour')+':'+pick('minute')+':'+pick('second')+' · '+label;
}
