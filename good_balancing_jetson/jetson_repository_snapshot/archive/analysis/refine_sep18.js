'use strict';
const E=require('../simulator175/engine.js'),fs=require('fs');
const base={duration:30,rail:.15,amax_s:12,amax_b:12,jmax:60,vmax:.8,encoderMs:1};const rows=[];
for(const ke of [6,8,10])for(const kpx of [30,80,150])for(const kdx of [1,2,4])for(const phase_soft of [1,2,3])for(const pw of [6,7]){
 const p={...base,ke,kpx,kdx,phase_soft,pw};const s=E.simulate(p).summary;
 if(s.status==='balanced'){
 const checks=[{}, {initialAngle:5},{initialAngle:-5},{leff:.118,damping:.42,coulomb:.4}].map(v=>E.simulate({...p,...v}).summary);
 rows.push({p,passes:checks.filter(s=>s.status==='balanced').length,checks});
 } }
rows.sort((a,b)=>b.passes-a.passes||b.checks.reduce((s,r)=>s+r.finalStable,0)-a.checks.reduce((s,r)=>s+r.finalStable,0));
fs.writeFileSync('analysis/sep18/gain_refinement.json',JSON.stringify({tested:162,rows},null,2));console.log('settled',rows.length);console.log(JSON.stringify(rows.slice(0,5),null,2));
