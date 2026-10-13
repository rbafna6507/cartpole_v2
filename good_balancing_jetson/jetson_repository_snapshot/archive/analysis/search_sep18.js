'use strict';
const E=require('../simulator175/engine.js'),fs=require('fs');
let seed=180926;function rng(){seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296;}const pick=a=>a[Math.floor(rng()*a.length)];
const rows=[];const base={duration:25,rail:.15,amax_s:12,amax_b:12,jmax:60,encoderMs:1};
for(let i=0;i<360;i++){
 const p={...base,ke:pick([1.5,2,3,4,5,6,8]),kpx:pick([10,20,30,50,80,120,150]),kdx:pick([.5,1,2,4,6,8]),phase_soft:pick([.2,.5,1,2]),vmax:pick([.4,.5,.6,.69,.8]),pw:pick([5,6,7,8])};
 const r=E.simulate(p);rows.push({p,summary:r.summary});
 if(i%40===0)console.log('tested',i,'balanced',rows.filter(x=>x.summary.status==='balanced').length);
}
rows.sort((a,b)=>(b.summary.finalStable-a.summary.finalStable)||(a.summary.recoverySeconds-b.summary.recoverySeconds));
fs.writeFileSync('analysis/sep18/gain_search_initial.json',JSON.stringify({seed:180926,rows},null,2));console.log(JSON.stringify(rows.slice(0,12),null,2));
