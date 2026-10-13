const E=require(process.cwd()+'/simulator175/engine.js'),fs=require('fs');
const variants=require(process.cwd()+'/simulator175/search_refinement.json').variants;
const good=[];let tested=0;
for(const a of [3.5,4,4.5,5])for(const b of [3.5,4,4.5,5,5.5,6])for(const j of [20,25,30,35])for(const v of [.55,.6,.65,.7,.75,.8]){
 const p={amax_s:a,amax_b:b,jmax:j,vmax:v,duration:30},s=E.simulate(p).summary;tested++;
 if(s.status!=='balanced')continue;
 const cases=variants.map(variant=>({variant,s:E.simulate({...p,...variant}).summary}));
 const score=cases.filter(c=>c.s.status==='balanced').length;
 good.push({p,score,cases});
}
good.sort((a,b)=>b.score-a.score||Math.max(a.p.amax_s,a.p.amax_b)-Math.max(b.p.amax_s,b.p.amax_b)||a.p.vmax-b.p.vmax||a.p.jmax-b.p.jmax);
fs.writeFileSync('simulator175/search_split_caps.json',JSON.stringify({tested,variants,results:good},null,2));
console.log('tested',tested,'nominal settled',good.length);console.log(JSON.stringify(good.slice(0,8).map(({p,score})=>({p,score})),null,2));
