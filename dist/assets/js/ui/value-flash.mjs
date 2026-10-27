// Values produced by a calculation (proposal, simulation, decision, risk
// window). Values the user drags directly, such as the valuation sliders,
// are excluded so they do not blink while being edited.
const VALUES =
  ".metric-value, .composition-metrics strong, .decision-stats strong, " +
  ".chart-summary strong, .forecast-band strong";
const CONTAINERS =
  ".metric-card, .composition-metrics > div, .decision-stats > div, " +
  ".chart-summary, .forecast-band";
const LABELS = ".metric-label, .summary-label, label";

/**
 * Records each value by key and returns, for every entry, how many
 * milliseconds ago it last changed. A value seen for the first time has no
 * change; one that differs from the previous render starts a new change.
 */
export function trackChanges(seen, entries, now) {
  return entries.map(({ key, value }) => {
    const previous = seen.get(key);
    const since = previous && previous.value !== value ? now : previous?.since ?? -Infinity;
    seen.set(key, { value, since });
    return now - since;
  });
}

/**
 * Highlights calculated values that changed since the last render. The app
 * rebuilds the whole shell on every state change, so a highlight in progress
 * is resumed on the new element at its elapsed time instead of restarting.
 */
export function createValueFlash({ duration = 1200 } = {}) {
  const seen = new Map();
  return {
    apply(root, scope) {
      const counts = new Map();
      const elements = [...root.querySelectorAll(VALUES)];
      const entries = elements.map((element) => {
        const box = element.closest(CONTAINERS) || element.parentElement;
        const label = box?.querySelector(LABELS)?.textContent.replace(/\s+/g, " ").trim() || "";
        const base = `${scope}|${label}`;
        const n = counts.get(base) || 0;
        counts.set(base, n + 1);
        return { key: n ? `${base}#${n}` : base, value: element.textContent.replace(/\s+/g, " ").trim() };
      });
      trackChanges(seen, entries, performance.now()).forEach((elapsed, i) => {
        if (elapsed >= duration) return;
        elements[i].classList.add("value-changed");
        elements[i].style.animationDelay = `-${Math.round(elapsed)}ms`;
      });
    },
  };
}
