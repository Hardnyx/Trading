/** Run the registered 2008-2019 out-of-sample test of the deployed price risk kernel. */
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {REPLAY_PROTOCOL,runPriceRiskReplay} from './price_risk_replay.mjs';

const design=JSON.parse(readFileSync('docs/estudio-riesgo-precios-2008-2019-v1.json','utf8'));
const engine=design.engine;
for(const [key,value] of Object.entries({id:engine.protocol_id,lead:engine.lead,minimumTraining:engine.minimum_training,
  lookback:engine.lookback,paths:engine.paths,seed:engine.seed}))
  if(REPLAY_PROTOCOL[key]!==value)throw Error('Deployed protocol differs from the registration: '+key);
const protocol=Object.freeze({...REPLAY_PROTOCOL,symbols:design.instruments,baskets:design.baskets});
const path=process.argv[2]||'out/price-risk-oos-market.json',bytes=readFileSync(path);
const report=runPriceRiskReplay(JSON.parse(bytes),{protocol,
  cutWindow:{first:design.period.first_cut,last:design.period.last_cut},onProgress:p=>console.log(JSON.stringify(p))});
report.market_sha256=createHash('sha256').update(bytes).digest('hex');
report.design_sha256=createHash('sha256').update(readFileSync('docs/estudio-riesgo-precios-2008-2019-v1.json')).digest('hex');
mkdirSync('out',{recursive:true});writeFileSync('out/price-risk-oos-replay.json',JSON.stringify(report)+'\n');
console.log(JSON.stringify({records:report.records.length,first:report.records[0]?.cut,last:report.records.at(-1)?.cut}));
