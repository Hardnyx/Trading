import { composePortfolio, reconcileStarts } from "./composer.mjs?v=0.34.1";

// One independent search per message, or the reconciliation of their winners
// on common paths (multi-start, see reconcileStarts).
self.onmessage = (event) => {
  const { id, kind = "compose", snapshot, settings, overrides, rules, proposals } = event.data;
  try {
    self.postMessage({
      id,
      proposal: kind === "reconcile"
        ? reconcileStarts(snapshot, settings, overrides, rules, proposals)
        : composePortfolio(snapshot, settings, overrides, rules, { deferRobustDecision: true }),
    });
  } catch (error) {
    self.postMessage({ id, error: error.message });
  }
};
