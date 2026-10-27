import {compareRobustPortfolio} from './robust-composer.mjs?v=0.21.0';
self.onmessage=({data})=>{
 const {id,snapshot,settings,overrides,rules,proposal,comparisonLabel}=data;
 try{
  const report=compareRobustPortfolio(snapshot,settings,overrides,rules,{
   proposal,comparisonLabel,onProgress:(phase,detail)=>self.postMessage({id,progress:{phase,detail}})});
  self.postMessage({id,report});
 }catch(error){self.postMessage({id,error:error.message});}
};
