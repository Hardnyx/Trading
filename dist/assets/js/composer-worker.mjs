import { composePortfolio } from "./composer.mjs?v=0.14.0";

self.onmessage = (event) => {
  const { id, snapshot, settings, overrides, rules } = event.data;
  try {
    self.postMessage({
      id,
      proposal: composePortfolio(snapshot, settings, overrides, rules),
    });
  } catch (error) {
    self.postMessage({ id, error: error.message });
  }
};
