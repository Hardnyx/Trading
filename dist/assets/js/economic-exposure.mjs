/* Economic ETF exposure. Never invent missing issuer holdings. */
export const TREASURY=new Set(["SHY","SGOV","BIL","IEI","IEF","TLT","TIP"]);
const CREDIT=new Set(["LQD","HYG","EMB"]);
const MIXED=new Set(["AGG","BND"]);
const GOLD=new Set(["GLD","IAU"]);
const INTL=new Set(["VXUS","VEA","VWO","EFA","EEM","EWJ","EWZ","EWW","ECH","EPU"]);
const US=new Set(["SPY","VTI","QQQ","IWM","XLK","XLC","XLY","XLP","XLF","XLE","XLV","XLI","XLU","XLRE","XLB","SMH","SOXX","VNQ","KRE"]);
const sectorETF={XLK:"Tecnología",XLC:"Comunicación",XLY:"Consumo discrecional",XLP:"Consumo básico",XLF:"Financiero",XLE:"Energía",XLV:"Salud",XLI:"Industrial",XLU:"Servicios públicos",XLRE:"Inmobiliario",XLB:"Materiales",SMH:"Tecnología",SOXX:"Tecnología",VNQ:"Inmobiliario",KRE:"Financiero"};
export function economicClass(a){
 if(a.type==="cash")return "cash";
 if(a.type==="stock")return "direct-equity";
 const s=a.symbol;
 if(TREASURY.has(s))return "treasury";
 if(CREDIT.has(s))return "credit";
 if(MIXED.has(s))return "mixed-bond";
 if(GOLD.has(s))return "gold";
 if(INTL.has(s))return "international-equity";
 if(US.has(s))return "us-equity";
 return a.type==="etf"?"unclassified-etf":"other";
}
export function actualHoldings(a,asOf,informationAsOf=asOf){
 const h=a.holdings;
 if(!h || !Array.isArray(h.positions) ||
    !/^\d{4}-\d\d-\d\d$/.test(h.as_of||"") || h.as_of>asOf ||
    !/^\d{4}-\d\d-\d\dT/.test(h.observed_at||"") ||
    h.observed_at.slice(0,10)>informationAsOf)return null;
 let coverage=0;const seen=new Set();
 for(const p of h.positions){
  if(!/^[A-Z0-9.-]{1,15}$/.test(p?.symbol||"") || seen.has(p.symbol) || !Number.isFinite(p.weight) || p.weight<0 || p.weight>1)return null;
  coverage+=p.weight;seen.add(p.symbol);
 }
 if(coverage>1.000001)return null;
 return {positions:h.positions,coverage,asOf:h.as_of,source_url:h.source_url||null};
}
export function exposureReport(assets,weights,asOf,informationAsOf=asOf,universeSectors={}){
 const knownSectors=new Map([
  ...Object.entries(universeSectors),
  ...assets.filter(a=>a.type==="stock").map(a=>[a.symbol,a.sector]),
 ]);
 const sleeves={treasury:0,credit:0,mixedBonds:0,usEquity:0,globalEquity:0,gold:0,unknownEtf:0},sectors={},issuers={},unknown=[],funds=[];
 for(let i=0;i<assets.length;i++){
  const a=assets[i],w=weights[i]||0;if(w<=1e-8)continue;
  const k=economicClass(a);
  if(k==="treasury")sleeves.treasury+=w;
  if(k==="credit")sleeves.credit+=w;
  if(k==="mixed-bond")sleeves.mixedBonds+=w;
  if(k==="us-equity"||k==="direct-equity")sleeves.usEquity+=w;
  if(k==="international-equity")sleeves.globalEquity+=w;
  if(k==="gold")sleeves.gold+=w;
  if(k==="unclassified-etf"){sleeves.unknownEtf+=w;unknown.push(a.symbol);}
  if(k==="direct-equity"){
    sectors[a.sector]=(sectors[a.sector]||0)+w;
    issuers[a.symbol]=(issuers[a.symbol]||0)+w;
  }
  if(a.type==="etf"){
   const sector=sectorETF[a.symbol];
   // Sector-specific ETFs are entirely assigned to their published mandate.
   // This applies whether or not an issuer-level holdings feed is present.
   if(sector)sectors[sector]=(sectors[sector]||0)+w;
   const h=actualHoldings(a,asOf,informationAsOf);
   funds.push({
     symbol:a.symbol,weight:w,economicGroup:k,
     holdingsAsOf:h?.asOf||null,
     firstObservedAt:h? a.holdings.observed_at:null,
     coveredWeight:h?.coverage??null,
     reportedCount:a.holdings?.positions_reported??null,
     topHoldings:h?.positions.slice(0,8)||[],
     sourceLayer:a.holdings?.source_layer||null,
     sourceUrl:h?.source_url||null,
     status:h?"fechadas y parcialmente reconocidas":"composición interna no validada",
   });
   if(h){
     let sectorCovered=0;
     for(const p of h.positions){
       issuers[p.symbol]=(issuers[p.symbol]||0)+w*p.weight;
       // Broad-market ETFs: allocate ONLY the issuer weights with a known
       // stock sector. Missing constituent classifications stay unassigned.
       if(!sector && knownSectors.has(p.symbol)){
         const group=knownSectors.get(p.symbol);
         sectors[group]=(sectors[group]||0)+w*p.weight;
         sectorCovered+=p.weight;
       }
     }
     if(h.coverage<.95)unknown.push(a.symbol+" (cobertura parcial)");
     if(!sector && sectorCovered+1e-8<h.coverage && k.includes("equity"))
       unknown.push(a.symbol+" (sectores de holdings parciales)");
   }else if(k==="us-equity"||k==="international-equity"){
     unknown.push(a.symbol+" (cartera no disponible)");
   }
  }
 }
 return {sleeves,sectors,issuers,funds,unknownHoldings:unknown,
   note:"Carteras subyacentes solo cuando el emisor proporcionó posiciones fechadas. La categoría Treasury proviene del mandato del ETF; no supone correlaciones perfectas ni inventa ponderaciones."};
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
