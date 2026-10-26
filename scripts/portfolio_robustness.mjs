/** Fixed-universe, paired-model, finite-pool minimax-regret research. Not a live trading signal. */
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {referenceRequest} from '../dist/assets/js/reference-preset.mjs?v=0.12.0';
import {compareRobustPortfolio} from '../dist/assets/js/robust-composer.mjs?v=0.12.0';

const market=JSON.parse(readFileSync('dist/data/market.json'));
const volatility=JSON.parse(readFileSync('dist/data/volatility.json'));
if(volatility.source_market_generated_at!==market.generated_at)throw Error('Inconsistent risk vintage');
const profiles=JSON.parse(readFileSync(process.argv[2]));
const config={candidateCount:1200,searchPaths:300,verificationPaths:1500,finalists:12,localRounds:3,localStarts:3,
  seed:20261026,...(process.argv[4]?JSON.parse(readFileSync(process.argv[4])):{})};
for(const key of ['candidateCount','searchPaths','verificationPaths','finalists','seed','localRounds','localStarts'])
 if(!Number.isInteger(config[key])||config[key]<1)throw Error('Invalid research configuration');
if(config.searchPaths<100||config.verificationPaths<100||config.candidateCount>10000||config.finalists>30||config.localRounds>6||config.localStarts>6)
 throw Error('Research budget outside supported bounds');
const snapshot={...market,volatility,assets:market.assets.map(a=>profiles[a.symbol]?{...a,bond_profile:profiles[a.symbol]}:a)};
const preset=referenceRequest(snapshot);
const shortRate=snapshot.macro.find(r=>r.id==='DGS3MO')?.value/100;
if(!Number.isFinite(shortRate))throw Error('Missing observed short-rate anchor');
const accountInput=JSON.parse(readFileSync(process.argv[3]));
if(!accountInput.account?.enabled)throw Error('Supply an explicit research account file');
// Explicit hypotheses for held funds. These are sensitivity inputs, not
// inferred analyst forecasts or validated asset-class expected returns.
const hypotheses={VTI:{expectedReturn:shortRate+.035,uncertainty:.15},
  GLD:{expectedReturn:0,uncertainty:.15}};
const settings={...preset.settings,seed:config.seed,assetAssumptions:hypotheses,
  account:accountInput.account};
const report=compareRobustPortfolio(snapshot,settings,{},preset.rules,{
 config,onProgress:(phase,detail)=>console.log(phase,detail)});
report.source_market_generated_at=market.generated_at;
report.information_observed_through=Object.values(profiles).map(p=>p.observed_at).concat(market.generated_at).sort().at(-1);
report.market_sha256=createHash('sha256').update(readFileSync('dist/data/market.json')).digest('hex');
report.explicit_etf_hypotheses=hypotheses;
report.issuer_profiles=profiles;
report.observation_basis=accountInput.basis;
mkdirSync('out',{recursive:true});writeFileSync('out/portfolio-robustness.json',JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({candidate:report.candidate?.positions,decision:report.decision,
 candidate_count:report.candidate_count,verified_candidates:report.verified_candidates,
 output:'out/portfolio-robustness.json'}));
