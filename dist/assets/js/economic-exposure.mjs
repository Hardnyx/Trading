import { observedBy } from "./observation.mjs?v=0.33.1";
/* Economic ETF exposure. Never invent missing issuer holdings. */
export const TREASURY=new Set(["SHY","SGOV","BIL","IEI","IEF","TLT","TIP","VGSH","VGIT","VGLT","SHV"]);
const CREDIT=new Set(["LQD","HYG","EMB","IGSB","VCIT","VCSH","JNK","BKLN"]);
// Credit below investment grade or emerging-market sovereign: a sub-sleeve
// of credit with its own prudential cap.
export const RISKY_CREDIT=new Set(["HYG","JNK","BKLN","EMB"]);
// Outside a US-only mandate: international and global equity (global funds
// hold about 40% outside the US) and foreign or emerging-market debt.
const FOREIGN_DEBT=new Set(["EMB","BNDX"]);
export function outsideUS(a){
 const k=economicClass(a);
 return k==="international-equity"||k==="global-equity"||FOREIGN_DEBT.has(a.symbol);
}
const MIXED=new Set(["AGG","BND","BNDX"]);
const GOLD=new Set(["GLD","IAU"]);
const INTL=new Set(["VXUS","VEA","VWO","EFA","EEM","EWJ","EWZ","EWW","ECH","EPU","INDA","MCHI","FXI","EWG","EWU","EWC","EWA","EWT","KWEB"]);
const US=new Set(["SPY","VTI","QQQ","IWM","XLK","XLC","XLY","XLP","XLF","XLE","XLV","XLI","XLU","XLRE","XLB","SMH","SOXX","VNQ","KRE","VTV","VUG","SCHD","QUAL","USMV","MTUM","RSP","DIA","VIG","DGRO","SPLV","XBI","IBB"]);
const WORLD=new Set(['VT','ACWI','URTH']);
for(const symbol of ['ACWX','SPDW','SPEM'])INTL.add(symbol);
for(const symbol of ['SCHB','ITOT','SCHX','VV','VO','VB','IJR','IJH','IWB','IWF','IWD','VBR','VOE','VOT','VBK','SPSM','SPTM'])US.add(symbol);
const sectorETF={XLK:"Tecnología",XLC:"Comunicación",XLY:"Consumo discrecional",XLP:"Consumo básico",XLF:"Financiero",XLE:"Energía",XLV:"Salud",XLI:"Industrial",XLU:"Servicios públicos",XLRE:"Inmobiliario",XLB:"Materiales",SMH:"Tecnología",SOXX:"Tecnología",VNQ:"Inmobiliario",KRE:"Financiero",XBI:"Salud",IBB:"Salud"};
export const HOLDINGS_MAX_AGE_DAYS=120;
// Listed share classes remain distinct instruments but share issuer risk.
export function issuerKey(symbol){
 return ({GOOG:"GOOGL","BRK.B":"BRK-B","BRK.A":"BRK-B","BRK-A":"BRK-B",
   "BF.B":"BF-B","BF.A":"BF-B","BF-A":"BF-B",FOX:"FOXA",NWS:"NWSA"})[symbol]||symbol;
}
export const issuerSymbol=issuerKey;
export function economicClass(a){
 if(a.type==="cash")return "cash";
 if(a.type==="stock")return "direct-equity";
 const s=a.symbol;
 if(TREASURY.has(s))return "treasury";
 if(CREDIT.has(s))return "credit";
 if(MIXED.has(s))return "mixed-bond";
 if(s==="MUB")return "municipal-bond";
 if(GOLD.has(s))return "gold";
 if(s==="SLV")return "silver";
 if(WORLD.has(s))return 'global-equity';
 if(INTL.has(s))return "international-equity";
 if(US.has(s))return "us-equity";
 return a.type==="etf"?"unclassified-etf":"other";
}
function validDate(value){
 return /^\d{4}-\d\d-\d\d$/.test(value||"") &&
   Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0,10)===value;
}
export function actualHoldings(a,asOf,informationAsOf=asOf){
 const h=a.holdings;
 if(!h || !Array.isArray(h.positions) ||
    !h.positions.length || !validDate(h.as_of) || h.as_of>asOf ||
    !/^\d{4}-\d\d-\d\dT.*(?:Z|[+-]\d\d:\d\d)$/.test(h.observed_at||"") ||
    !Number.isFinite(Date.parse(h.observed_at)) ||
    !observedBy(h.observed_at,informationAsOf))return null;
 const ageDays=(Date.parse(informationAsOf)-Date.parse(h.as_of))/86400000;
 if(!Number.isFinite(ageDays) || ageDays<0 || ageDays>HOLDINGS_MAX_AGE_DAYS)return null;
 let coverage=0;const seen=new Set();
 for(const p of h.positions){
  if(!/^[A-Z0-9.-]{1,15}$/.test(p?.symbol||"") || seen.has(p.symbol) || !Number.isFinite(p.weight) || p.weight<0 || p.weight>1)return null;
  coverage+=p.weight;seen.add(p.symbol);
 }
 if(coverage>1.050001)return null; // small gross leverage kept as exposure, never rescaled
 return {positions:h.positions,coverage,ageDays,asOf:h.as_of,source_url:h.source_url||null};
}
export function exposureReport(assets,weights,asOf,informationAsOf=asOf,universeSectors={}){
 const knownSectors=new Map([
  ...Object.entries(universeSectors).map(([s,v])=>[issuerKey(s),v]),
  ...assets.filter(a=>a.type==="stock").map(a=>[issuerKey(a.symbol),a.sector]),
 ]);
 const sleeves={treasury:0,credit:0,riskyCredit:0,mixedBonds:0,municipalBonds:0,usEquity:0,globalEquity:0,gold:0,silver:0,unknownEtf:0},sectors={},issuers={},unknown=[],funds=[],unknownIssuerBlocks=[];
 let unclassifiedSectorWeight=0;
 for(let i=0;i<assets.length;i++){
  const a=assets[i],w=weights[i]||0;if(w<=1e-8)continue;
  const k=economicClass(a);
  if(k==="treasury")sleeves.treasury+=w;
  if(k==="credit")sleeves.credit+=w;
  if(RISKY_CREDIT.has(a.symbol))sleeves.riskyCredit+=w;
  if(k==="mixed-bond")sleeves.mixedBonds+=w;
  if(k==="municipal-bond")sleeves.municipalBonds+=w;
  if(k==="us-equity"||k==="direct-equity")sleeves.usEquity+=w;
  if(k==="international-equity"||k==='global-equity')sleeves.globalEquity+=w;
  if(k==="gold")sleeves.gold+=w;
  if(k==="silver")sleeves.silver+=w;
  if(k==="unclassified-etf"){sleeves.unknownEtf+=w;unknown.push(a.symbol);}
  if(k==="direct-equity"){
    sectors[a.sector]=(sectors[a.sector]||0)+w;
    const key=issuerKey(a.symbol);
    issuers[key]=(issuers[key]||0)+w;
  }
  if(a.type==="etf"){
   const sector=sectorETF[a.symbol];
   // Sector-specific ETFs are entirely assigned to their published mandate.
   // This applies whether or not an issuer-level holdings feed is present.
   if(sector)sectors[sector]=(sectors[sector]||0)+w;
   const h=actualHoldings(a,asOf,informationAsOf);
   const equity=k==="us-equity"||k==="international-equity"||k==='global-equity';
   const missing=Math.max(0,1-(h?.coverage||0));
   if(equity)unknownIssuerBlocks.push({weight:w*missing,
     known:new Set((h?.positions||[]).map(p=>issuerKey(p.symbol)))});
   funds.push({
     symbol:a.symbol,weight:w,economicGroup:k,
     holdingsAsOf:h?.asOf||null,
     holdingsAgeDays:h?.ageDays??null,
     firstObservedAt:h? a.holdings.observed_at:null,
     coveredWeight:h?.coverage??null,
     reportedCount:a.holdings?.positions_reported??null,
     topHoldings:h?[...h.positions].sort((a,b)=>b.weight-a.weight).slice(0,8):[],
     sourceLayer:a.holdings?.source_layer||null,
     sourceUrl:h?.source_url||null,
     status:h?"fechadas y parcialmente reconocidas":"composición interna no validada",
   });
   if(h){
     let sectorCovered=0;
     for(const p of h.positions){
       const key=issuerKey(p.symbol);
       issuers[key]=(issuers[key]||0)+w*p.weight;
       // Broad-market ETFs: allocate ONLY the issuer weights with a known
       // stock sector. Missing constituent classifications stay unassigned.
       if(!sector && knownSectors.has(key)){
         const group=knownSectors.get(key);
         sectors[group]=(sectors[group]||0)+w*p.weight;
         sectorCovered+=p.weight;
       }
     }
     if(equity && !sector)unclassifiedSectorWeight+=w*Math.max(0,1-sectorCovered);
     if(h.coverage<1-1e-6)unknown.push(a.symbol+" (cobertura parcial)");
     if(!sector && sectorCovered+1e-8<h.coverage && k.includes("equity"))
       unknown.push(a.symbol+" (sectores de holdings parciales)");
   }else if(equity){
     if(!sector)unclassifiedSectorWeight+=w;
     unknown.push(a.symbol+" (cartera no disponible)");
   }
  }
 }
 const unclassifiedIssuerWeight=unknownIssuerBlocks.reduce((s,b)=>s+b.weight,0);
 // These are conservative bounds, NOT invented constituent allocations.
 // An unidentified tail can belong to any otherwise unobserved issuer/sector.
 const issuerUpperBounds=Object.fromEntries(Object.entries(issuers).map(([key,w])=>
   [key,w+unknownIssuerBlocks.filter(b=>!b.known.has(key)).reduce((s,b)=>s+b.weight,0)]));
 const sectorUpperBounds=Object.fromEntries(Object.entries(sectors).map(([key,w])=>
   [key,w+unclassifiedSectorWeight]));
 return {sleeves,sectors,issuers,funds,unknownHoldings:[...new Set(unknown)],
   issuerUpperBounds,sectorUpperBounds,unclassifiedIssuerWeight,unclassifiedSectorWeight,
   note:"Holdings conocidas hace no más de 120 días; clases de acciones agregadas por emisor. La parte desconocida se conserva como cota de concentración, no como diversificación demostrada. Treasury se clasifica por mandato; no se presume correlación perfecta."};
}
export function holdingsOverlap(a,b,asOf,informationAsOf=asOf){
 const positions=asset=>asset.type==="stock"?[{symbol:asset.symbol,weight:1}]:
   actualHoldings(asset,asOf,informationAsOf)?.positions;
 const left=positions(a),right=positions(b);
 if(!left||!right)return null;
 const aggregate=rows=>{
  const m=new Map();
  for(const p of rows){const key=issuerKey(p.symbol);m.set(key,(m.get(key)||0)+p.weight);}
  return m;
 };
 const la=aggregate(left),rb=aggregate(right);
 const shared=[...la].filter(([s])=>rb.has(s)).map(([symbol,w])=>
   ({symbol,leftWeight:w,rightWeight:rb.get(symbol)}));
 return {knownOverlap:shared.reduce((s,p)=>s+Math.min(p.leftWeight,p.rightWeight),0),
   leftCoverage:left.reduce((s,p)=>s+p.weight,0),
   rightCoverage:right.reduce((s,p)=>s+p.weight,0),shared};
}
/** Lower bound for duplicated ETF constituent weight, only on dated observations. */
export function knownFundOverlap(a,b,asOf,informationAsOf=asOf){
 const x=actualHoldings(a,asOf,informationAsOf),y=actualHoldings(b,asOf,informationAsOf);
 if(!x||!y)return {available:false,reason:"Requiere carteras fechadas y conocidas al corte"};
 const left=new Map();
 for(const p of x.positions){
   const key=issuerSymbol(p.symbol);
   left.set(key,(left.get(key)||0)+p.weight);
 }
 const right=new Map();
 for(const p of y.positions){
   const key=issuerSymbol(p.symbol);
   right.set(key,(right.get(key)||0)+p.weight);
 }
 let lowerBound=0;
 for(const [key,value] of left)
   lowerBound+=Math.min(value,right.get(key)||0);
 const missingA=Math.max(0,1-x.coverage),missingB=Math.max(0,1-y.coverage);
 return {
   available:true,lowerBound,
   looseUpperBound:Math.min(1,lowerBound+missingA+missingB),
   coverageA:x.coverage,coverageB:y.coverage,
   sourceDates:[x.asOf,y.asOf],
   note:"Intersección mínima observada sobre participaciones conocidas. La exposición no cubierta podría coincidir más.",
 };
}
export function rawCorrelation(cov,i,j){
 return cov[i][i]>0&&cov[j][j]>0?cov[i][j]/Math.sqrt(cov[i][i]*cov[j][j]):0;
}
export function qualifiedOpportunity(a,e,asOf){
 return !!e && e.source==="prospective-journal" &&
   e.validation==="independently-reviewed" && e.symbol===a.symbol &&
   /^\d{4}-\d\d-\d\d$/.test(e.as_of||"") && e.as_of<=asOf &&
   e.oosMatured>=126 && Number.isFinite(e.netAlphaLower95) &&
   e.netAlphaLower95>.02 && Number.isFinite(e.costAdjustedExpectedAlpha) &&
   e.costAdjustedExpectedAlpha>e.netAlphaLower95 &&
   e.factorOverlapReviewed===true && e.liquidityReviewed===true &&
   e.parameterUncertaintyReviewed===true;
}
