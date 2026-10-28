// Information cuts are New York calendar dates (see informationDate). An
// observation's timestamp is compared on that same calendar: a capture at
// 00:12 UTC on the 28th happened at 20:12 on the 27th in New York.
const NEW_YORK = new Intl.DateTimeFormat("en-CA", {
  timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit",
});
export function observationDate(timestamp) {
  const time = Date.parse(timestamp || "");
  return Number.isFinite(time) ? NEW_YORK.format(time) : null;
}
/** True when the observation is known by the end of the cut's New York day. */
export function observedBy(timestamp, cut) {
  const day = observationDate(timestamp);
  return day !== null && !!cut && day <= cut;
}
