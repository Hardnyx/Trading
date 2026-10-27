const files = [
  "components",
  "layout",
  "portfolio",
  "overview",
  "research",
  "forecasts",
  "risk",
  "valuation",
  "macro",
  "dialogs",
  "plot-lines",
  "plot-risk",
  "plot-forecast",
  "composition",
  "decision",
];

const escapeText = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (char) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[char],
  );

/**
 * HTML lives in external templates. Text and attributes are escaped by default.
 * Triple braces accept fragments already rendered by the views and charts.
 * Placeholders are substituted once; no JavaScript is evaluated from HTML.
 */
export function createTemplateRenderer(sources) {
  const registry = new Map();
  for (const source of sources) {
    const blocks = source.matchAll(
      /<template\s+id="([a-z][a-z0-9-]*)">\s*\n([\s\S]*?)\n\s*<\/template>/g,
    );
    for (const [, id, markup] of blocks) {
      if (registry.has(id)) throw new Error(`Plantilla duplicada: ${id}`);
      registry.set(id, markup.trim());
    }
  }
  if (!registry.size)
    throw new Error("No se encontraron plantillas de interfaz.");
  return (id, values = {}) => {
    if (!registry.has(id)) throw new Error(`Plantilla no disponible: ${id}`);
    return registry
      .get(id)
      .replace(
        /\{\{\{\s*(\w+)\s*\}\}\}|\{\{\s*(\w+)\s*\}\}/g,
        (_, fragment, text) => {
          const key = fragment || text;
          if (!Object.hasOwn(values, key))
            throw new Error(`Falta ${key} en la plantilla ${id}`);
          return fragment ? String(values[key] ?? "") : escapeText(values[key]);
        },
      );
  };
}

let renderTemplate;
let loading;

export function loadTemplates(fetcher = globalThis.fetch) {
  loading ||= Promise.all(
    files.map(async (file) => {
      const response = await fetcher(
        new URL(`../../../templates/${file}.html?v=0.26.0`, import.meta.url),
        { cache: "no-store" },
      );
      if (!response.ok)
        throw new Error(`No se pudo cargar la interfaz: ${file}.`);
      return response.text();
    }),
  )
    .then((sources) => {
      renderTemplate = createTemplateRenderer(sources);
    })
    .catch((error) => {
      loading = null;
      throw error;
    });
  return loading;
}

export function template(id, values) {
  if (!renderTemplate) throw new Error("Las plantillas aún no están cargadas.");
  return renderTemplate(id, values);
}
