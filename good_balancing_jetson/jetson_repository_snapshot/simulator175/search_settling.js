'use strict';
const E=require('./engine'),fs=require('fs');
const calibration=[
 {leff:.1657999240684903,damping:.3977323845595205},
 {leff:.16577556772475696,damping:.40817978142027395},
 {leff:.1650773031776556,damping:.4022789826050984}
];
const stress=[{initialAngle:1},{initialAngle:-1},{initialX:.005},{initialX:-.005},{leff:.163},{leff:.169},{damping:.32},{damping:.48},{delayMs:2},{lagMs:5},{tracking:.98}];
let seed=1752026, tested=0,nominal=0,calibrated=0;const survivors=[];
function rnd(){seed=(Math.imul(1664525,seed)+1013904223)>>>0;return seed/4294967296;}
function pick(xs){return xs[Math.floor(rnd()*xs.length)];}
for(let i=0;i<2000;i++){
 const p={duration:30,amax_s:pick([3,3.5,4,4.5,5,5.5,6]),amax_b:pick([4,4.5,5,5.5,6]),
  jmax:pick([20,25,30,40,50,60,75,100]),vmax:pick([.5,.55,.6,.65,.7,.75,.8,.9]),
  ke:pick([1.5,2,2.5,3,3.5,4]),kpx:pick([15,20,25,30,35,40]),kdx:pick([.25,.5,1,1.5,2]),phase_soft:pick([.5,1,1.5,2])};
 tested++;let s=E.simulate(p).summary;if(s.status!=='balanced')continue;nominal++;
 const cases=[{variant:{},s}];let valid=true;
 for(const variant of calibration){s=E.simulate({...p,...variant}).summary;cases.push({variant,s});if(s.status!=='balanced'){valid=false;break;}}
 if(!valid)continue;calibrated++;
 for(const variant of stress)cases.push({variant,s:E.simulate({...p,...variant}).summary});
 const score=cases.filter(c=>c.s.status==='balanced').length;
 survivors.push({p,score,cases});
 if(score===15)console.log('All 15 passed',JSON.stringify(p));
}
survivors.sort((a,b)=>b.score-a.score||Math.max(a.p.amax_s,a.p.amax_b)-Math.max(b.p.amax_s,b.p.amax_b)||a.p.vmax-b.p.vmax||a.p.jmax-b.p.jmax);
fs.writeFileSync(__dirname+'/search_settling_results.json',JSON.stringify({seed:1752026,tested,nominal,calibrated,calibration,stress,results:survivors},null,2));
console.log(JSON.stringify({tested,nominal,calibrated,best:survivors.slice(0,6).map(({p,score})=>({p,score}))},null,2));
