const bounded = (value, min, max) => {
  const number = Number(value);
  return Number.isFinite(number) ? Math.min(max, Math.max(min, number)) : min;
};

// Only numeric values derived from data cross into CSS custom properties.
// Colors, layout rules, spacing and all other presentation stay in CSS.
export function applyVisualValues(root) {
  const bindings = [
    ["[data-width]", "width", "--value-width", 0, 100, "%"],
    [
      "[data-marker-position]",
      "markerPosition",
      "--marker-position",
      0,
      100,
      "%",
    ],
    ["[data-heat-opacity]", "heatOpacity", "--heat-opacity", 0, 1, ""],
    ["[data-columns]", "columns", "--columns", 1, 100, ""],
  ];
  for (const [selector, attribute, property, min, max, unit] of bindings) {
    for (const element of root.querySelectorAll(selector)) {
      element.style.setProperty(
        property,
        bounded(element.dataset[attribute], min, max) + unit,
      );
    }
  }
}

export function showStartupError(error) {
  const content = document
    .getElementById("startup-error")
    .content.cloneNode(true);
  content.querySelector("[data-error-message]").textContent =
    error.message || "No se pudo cargar la aplicación.";
  document.getElementById("app").replaceChildren(content);
}
