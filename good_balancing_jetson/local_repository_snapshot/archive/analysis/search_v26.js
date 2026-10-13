const E=require('../simulator175/engine'),fs=require('fs'),D=require('./sep18/final_validation.json');
const base={ke:8,kpx:80,kdx:2,phase_soft:2,vmax_s:.8,duration:40};const cases=D.results[0].checks.map(c=>c.variant);const good=[];
for(const approach_angle of [.8,1,1.2,1.4])for(const approach_v of [.2,.3,.4])for(const catch_v of [.3,.4])for(const catch_da of [4,6]){
 const p={...base,approach_angle,approach_v,catch_v,catch_da};const s=E.simulate(p).summary;if(s.status==='balanced')good.push({p,initial:s});
}
console.log('nominal candidates',good.length);
for(const c of good){c.cases=cases.map(v=>E.simulate({...c.p,...v}).summary);c.passes=c.cases.filter(s=>s.status==='balanced').length;}
good.sort((a,b)=>b.passes-a.passes||b.cases.reduce((n,s)=>n+s.finalStable,0)-a.cases.reduce((n,s)=>n+s.finalStable,0));fs.writeFileSync('analysis/v26/search.json',JSON.stringify({cases,tested:48,good},null,2));console.log(good.slice(0,4).map(({p,passes})=>({p,passes})));
