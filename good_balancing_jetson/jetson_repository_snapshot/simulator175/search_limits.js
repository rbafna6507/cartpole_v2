'use strict';
// Reproducible search, keeping calibrated plant and actual motion style fixed.
const E=require('./engine.js'),fs=require('node:fs');
const results=[];
for(const a of [2,3,4,5,6])for(const j of [30,50,75,100,120,150])for(const v of [.4,.5,.6,.7,.8,.9,1]){
 const p={amax_s:a,amax_b:a,jmax:j,vmax:v,duration:30};
 const r=E.simulate(p),s=r.summary;
 if(s.status==='balanced'){
  const tail=r.trace.filter(x=>x.t>25),rms=k=>Math.sqrt(tail.reduce((a,x)=>a+x[k]**2,0)/tail.length);
  results.push({p,summary:s,tail:{rmsAngleDeg:rms('theta')*180/Math.PI,rmsXmm:rms('x')*1000,rmsV:rms('actualV')}});
 }
}
results.sort((a,b)=>a.p.amax_s-b.p.amax_s||a.p.vmax-b.p.vmax||a.p.jmax-b.p.jmax);
fs.writeFileSync(__dirname+'/search_results.json',JSON.stringify({tested:210,results},null,2));
console.log('Settled',results.length,'of 210');console.log(JSON.stringify(results.slice(0,12),null,2));
