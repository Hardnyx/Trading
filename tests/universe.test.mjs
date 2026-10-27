import test from "node:test";
import assert from "node:assert/strict";
import { selectCompositionUniverse, MAX_COMPOSITION_ASSETS } from "../dist/assets/js/universe.mjs";
import {compositionUniverseLimit} from '../dist/assets/js/composer.mjs?v=0.15.0';

test('expanded search budget retains defaults and supports bounded 60/80-asset samples',()=>{
 assert.equal(compositionUniverseLimit(),40);
 assert.equal(compositionUniverseLimit({compositionUniverseLimit:80}),80);
 assert.equal(compositionUniverseLimit({researchUniverseLimit:30}),30);
 assert.throws(()=>compositionUniverseLimit({compositionUniverseLimit:81}),/20 y 80/);
 const assets=Array.from({length:120},(_,i)=>asset('A'+i,'Sector'+i%10));
 assert.equal(selectCompositionUniverse(assets,['A119'],'SPY',80).assets.length,80);
 assert.ok(selectCompositionUniverse(assets,['A119'],'SPY',80).assets.some(a=>a.symbol==='A119'));
 assert.throws(()=>selectCompositionUniverse(assets,[],'SPY',81),/inválido/);
});

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
  assert.throws(()=> selectCompositionUniverse([], [], "SPY", 2),/[Ll]ímite/);
  const assets = [asset("CASH","Efectivo"), asset("CASH","Efectivo"), asset("SPY","Índice")];
  assert.equal(selectCompositionUniverse(assets).assets.length,2);
});

test("forward-valued names can enter the shortlist even if share volume is lower",()=>{
  const names=[asset("CASH","Efectivo",0,"cash"),asset("SHY","Treasuries",1),
    asset("SPY","Índice",100)];
  for(let i=0;i<50;i++)names.push(asset("N"+i,"Sector "+(i%6),1000+i));
  const signals=Object.fromEntries(names.map(a=>[a.symbol,0.02]));
  signals.N47=0.18;signals.N48=0.15;signals.N49=0.12;
  const selected=selectCompositionUniverse(names,[],"SPY",14,signals);
  for(const symbol of ["N47","N48","N49"])assert.ok(selected.assets.some(a=>a.symbol===symbol));
  assert.equal(selected.method,"auditable-forward-risk-adjusted-signal-and-sector-breadth");
  const swapped=structuredClone(names);
  swapped.find(a=>a.symbol==="N49").history.at(-1).close=1e6;
  assert.deepEqual(selectCompositionUniverse(swapped,[],"SPY",14,signals)
    .assets.map(a=>a.symbol),selected.assets.map(a=>a.symbol));
});
