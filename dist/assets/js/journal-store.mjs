// Keep long-horizon origins outside the small localStorage budget.
let database;
const known = new Map();
export async function openJournal() {
  if (!globalThis.indexedDB)
    throw new Error("El navegador no ofrece almacenamiento de previsiones.");
  database = await new Promise((resolve, reject) => {
    const request = indexedDB.open("trading-research", 1);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains("journal"))
        request.result.createObjectStore("journal", { keyPath: "id" });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
    request.onblocked = () =>
      reject(new Error("El registro está bloqueado por otra pestaña."));
  });
  const rows = await new Promise((resolve, reject) => {
    const request = database
      .transaction("journal", "readonly")
      .objectStore("journal")
      .getAll();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  rows.forEach((row) => known.set(row.id, !!row.outcome));
  return rows.sort((a, b) =>
    a.origin.created_at.localeCompare(b.origin.created_at),
  );
}
export function saveJournal(rows) {
  if (!database)
    return Promise.reject(new Error("El registro no está disponible."));
  const changed = rows.filter(
    (row) => !known.has(row.id) || !!row.outcome !== known.get(row.id),
  );
  if (!changed.length) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const transaction = database.transaction("journal", "readwrite"),
      store = transaction.objectStore("journal");
    for (const row of changed) store.put(structuredClone(row));
    transaction.oncomplete = () => {
      changed.forEach((row) => known.set(row.id, !!row.outcome));
      resolve();
    };
    transaction.onerror = () => reject(transaction.error);
    transaction.onabort = () =>
      reject(transaction.error || new Error("No se guardó el registro."));
  });
}
