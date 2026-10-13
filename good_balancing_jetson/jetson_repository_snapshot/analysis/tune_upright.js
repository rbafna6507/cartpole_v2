'use strict';
const fs=require('fs'),crypto=require('crypto'),E=require('../simulator175/engine');
const fit=require('../pendulum_characterization/175mm_14p2g/2026-09-15/controller_fit.json');
const cases=[];
for(const a of [-5,-2,2,5])cases.push({name:`release ${a}deg`,initialAngle:a});
for(const sign of [-1,1]){
 cases.push({name:`outward rate ${sign}`,initialAngle:sign*3,initialOmega:sign*.2});
 cases.push({name:`cart offset ${sign}`,initialAngle:sign*3,initialX:sign*.01});
 cases.push({name:`delay ${sign}`,initialAngle:sign*5,delayMs:2,lagMs:5});
 cases.push({name:`tracking ${sign}`,initialAngle:sign*5,tracking:.95,lagMs:5});
}
for(const [i,f] of fit.runs.entries())for(const sign of [-1,1])cases.push({name:`fit ${i+1}, ${sign}`,initialAngle:sign*5,leff:f.effective_length_m,damping:f.equivalent_viscous_decay_per_s});
function run(pw,c,duration=20){
 const {name,...variant}=c,r=E.simulate({scenario:'balance',duration,bal_pw:pw,...variant});
 const tail=r.trace.filter(x=>x.t>=duration-5),rms=k=>Math.sqrt(tail.reduce((v,x)=>v+x[k]**2,0)/tail.length);
 let lastOutside=0;for(const x of r.trace)if(Math.abs(x.theta)>2*Math.PI/180||Math.abs(x.x)>.01||Math.abs(x.actualV)>.02||x.mode!=='balance')lastOutside=x.t;
 return {name,variant,summary:r.summary,events:r.events,angleRmsDeg:rms('theta')*180/Math.PI,xRmsMm:rms('x')*1000,settleS:lastOutside<duration-5?lastOutside:null};
}
const search=[6,7,8,9,10,11,12].map(pw=>{const results=cases.map(c=>run(pw,c));return {pw,passed:results.filter(r=>r.settleS!==null&&!r.events.length&&!r.summary.fault).length,peakX:Math.max(...results.map(r=>r.summary.peakX)),results};});
const evidence={engineSha256:crypto.createHash('sha256').update(fs.readFileSync('simulator175/engine.js')).digest('hex'),constraints:{vmax:.8,amax_s:12,amax_b:12,jmax:60,rail:.15},selectedBalPw:8,selectionReason:"Small first change from 7; all screening cases settle, reduced travel and settling time; larger settings cost more acceleration and 12 fails two cases.",caseCount:cases.length,search};
fs.writeFileSync('analysis/upright_tuning.json',JSON.stringify(evidence,null,2));
console.log(JSON.stringify(search.map(({pw,passed,peakX,results})=>({pw,passed,peakX,nominal:results.find(x=>x.name==='release 5deg')})),null,2));
