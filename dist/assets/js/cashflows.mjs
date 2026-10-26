/* Yahoo adjusted close already embeds distributions. Reclassify, never add twice. */
export function annualDistributionYield(asset) {
  if(asset.type==="cash"||!(asset.price>0))return 0;
  const dividend=asset.dividend_per_share;
  if(!Number.isFinite(dividend)||dividend<=0||dividend/asset.price>.25)return 0;
  return dividend/asset.price;
}
export function dividendStep(priorTotalGross,totalGross,annualYield,t,dt,withholding=0) {
  if(!annualYield)return {priceGross:totalGross,grossCash:0,netCash:0};
  const periodFactor=Math.pow(1+annualYield,dt);
  const priorPrice=priorTotalGross/Math.pow(1+annualYield,(t-1)*dt);
  const grossCash=priorPrice*(periodFactor-1);
  return {priceGross:totalGross/Math.pow(1+annualYield,t*dt),
    grossCash,netCash:grossCash*(1-withholding)};
}
