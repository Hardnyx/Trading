import { simulateForecast, validateRiskBands } from "./forecast.mjs?v=0.10.0";
self.onmessage = (event) => {
  const { id, assets, positions, options, overrides } = event.data;
  try {
    const forecast = simulateForecast(assets, positions, options, overrides);
    const validation = validateRiskBands(
      assets,
      positions,
      options.lambda || 0.94,
    );
    self.postMessage({ id, forecast, validation });
  } catch (error) {
    self.postMessage({ id, error: error.message });
  }
};
