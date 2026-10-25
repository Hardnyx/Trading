import test from "node:test";
import assert from "node:assert/strict";
import { selectCompositionUniverse, MAX_COMPOSITION_ASSETS } from "../dist/assets/js/universe.mjs";

const asset = (symbol, sector, volume=1000, type="etf") => ({
  symbol, sector, type, history: Array.from({length: 30}, (_, i) => ({
    date: `2026-09-${String(i+1).padStart(2,"0")}`,
    close: 10, volume,
  })),
});

test("shortlisting is deterministic, bounded and retains the current account", () => {
  const universe = [
    asset("CASH","Efectivo",0,"cash"), asset("SHY","Treasuries cortos"), asset("SPY","Índice amplio"),
    ...Array.from({length: 120}, (_, i) => asset(`T${i}`, `Sector ${i%12}`, 200+i)),
  ];
  const first = selectCompositionUniverse(universe, ["T112", "T99"]);
  const second = selectCompositionUniverse(universe, ["T112", "T99"]);
  assert.deepEqual(first, second);
  assert.equal(first.assets.length, MAX_COMPOSITION_ASSETS);
  const names = first.assets.map(a=>a.symbol);
  for(const symbol of ["CASH","SHY","SPY","T112","T99"]) assert.ok(names.includes(symbol));
  assert.equal(new Set(names).size,names.length);
  assert.equal(first.assets.length + first.omitted.length,universe.length);
  assert.ok(new Set(first.assets.map(a=>a.sector)).size >= 12);
});

test("shortlisting does not select past winners based on price return", () => {
  const assets = [asset("CASH","Efectivo"),...Array.from({length:12}, (_, i) => asset(`A${i}`,`Sector ${i%3}`,i+1))];
  const before = selectCompositionUniverse(assets, [], "NONE", 6);
  for (const a of assets) a.history.at(-1).close = a.symbol==="A0" ? 100000 : 1;
  const after = selectCompositionUniverse(assets, [], "NONE", 6);
  assert.deepEqual(after.assets.map(a=>a.symbol),before.assets.map(a=>a.symbol));
});

test("no duplicate eligible assets and invalid cap rejected", () => {
  assert.throws(()=> selectCompositionUniverse([], [], "SPY", 2),/límite/);
  const assets = [asset("CASH","Efectivo"), asset("CASH","Efectivo"), asset("SPY","Índice")];
  assert.equal(selectCompositionUniverse(assets).assets.length,2);
});
