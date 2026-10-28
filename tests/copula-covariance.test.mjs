import test from 'node:test';
import assert from 'node:assert/strict';
import {copulaInnovationCovariance} from '../dist/assets/js/copula-covariance.mjs?v=0.29.0';
import {cholesky} from '../dist/assets/js/risk-math.mjs?v=0.29.0';

test('Gaussian marginals preserve the input; t marginals report their induced linear covariance',()=>{
 const latent=[[.04,.054],[.054,.09]];
 assert.equal(copulaInnovationCovariance(latent,[null,null]).covariance,latent);
 const result=copulaInnovationCovariance(latent,[{nu:4.0429192584},null]);
 const c=result.covariance,rho=c[0][1]/Math.sqrt(c[0][0]*c[1][1]);
 assert.ok(Math.abs(rho-.871412)<3e-6);
 assert.ok(Math.abs(result.maxCorrelationShift-(.9-rho))<1e-10);
 assert.ok(Math.abs(c[0][0]-.04)<1e-6);
 assert.ok(result.projectionRemainderMaximum<1e-5);
 assert.doesNotThrow(()=>cholesky(c));
 assert.deepEqual(latent,[[.04,.054],[.054,.09]]);
});

test('mixed marginal projections remain PSD and preserve zero-variance cash',()=>{
 const c=[[1,.9,-.6,0],[.9,1,-.7,0],[-.6,-.7,1,0],[0,0,0,0]];
 const result=copulaInnovationCovariance(c,[{nu:4.5},{nu:8},null,null]);
 assert.doesNotThrow(()=>cholesky(result.covariance));
 assert.deepEqual(result.covariance[3],[0,0,0,0]);
 assert.ok(result.covariance[0][2]<0);
 assert.equal(result.covariance[1][0],result.covariance[0][1]);
});
