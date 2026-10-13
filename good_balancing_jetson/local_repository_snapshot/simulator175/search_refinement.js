const E=require(process.cwd()+'/simulator175/engine.js'),fs=require('fs');
const variants=[{}, {initialAngle:1},{initialAngle:-1},{initialX:.005},{initialX:-.005},{leff:.163},{leff:.169},{damping:.32},{damping:.48},{delayMs:2},{lagMs:5},{tracking:.98}];
const good=[];let tested=0;
for(const a of [4,4.5,5,5.5,6])for(const j of [20,25,30,35,40,45,50,60,75])for(const v of [.65,.7,.75,.8,.85,.9,1]){
 const p={amax_s:a,amax_b:a,jmax:j,vmax:v,duration:30},s=E.simulate(p).summary;tested++;
 if(s.status!=='balanced')continue;
 const cases=variants.map(variant=>({variant,s:E.simulate({...p,...variant}).summary}));
 const score=cases.filter(c=>c.s.status==='balanced').length;
 good.push({p,score,cases});
}
good.sort((a,b)=>b.score-a.score||a.p.amax_s-b.p.amax_s||a.p.vmax-b.p.vmax||a.p.jmax-b.p.jmax);
fs.writeFileSync('simulator175/search_refinement.json',JSON.stringify({tested,variants,results:good},null,2));
console.log('tested',tested,'nominal settled',good.length);console.log(JSON.stringify(good.slice(0,12).map(({p,score})=>({p,score})),null,2));
