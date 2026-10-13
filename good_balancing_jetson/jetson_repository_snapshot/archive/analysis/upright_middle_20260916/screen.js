'use strict';
// Sensitivity experiments only: no controller source or live parameters changed.
const fs=require('fs'),vm=require('vm'),path=require('path');
const root=path.resolve(__dirname,'../..');let source=fs.readFileSync(path.join(root,'simulator175/engine.js'),'utf8');
source=source.replace('hat=q,rate=p.initialOmega,measured=q','hat=q+(p.sensorBias||0),rate=p.initialOmega,measured=q+(p.sensorBias||0)');
source=source.replace('Math.round(q*4096/(2*PI))','Math.round((q+(p.sensorBias||0))*4096/(2*PI))');
source=source.replace('k[0]*hat+k[1]*rate','k[0]*(hat-(p.trim||0))+k[1]*rate');
const ctx={module:{exports:{}}};vm.runInNewContext(source,ctx);const E=ctx.module.exports;
const results=[];const DEG=Math.PI/180;
for(const bal_pw of [6,7,8])for(const pz of [.85,1,1.1])for(const lagMs of [0,20,40,60])for(const tracking of [.6,.8,1]){
 const p={scenario:'balance',duration:20,initialAngle:2,bal_pw,pz,lagMs,tracking,sensorBias:.234*DEG,trim:.2*DEG};
 const r=E.simulate(p),tail=r.trace.filter(x=>x.t>=15);const rms=k=>Math.sqrt(tail.reduce((a,x)=>a+x[k]**2,0)/tail.length);
 results.push({bal_pw,pz,lagMs,tracking,status:r.summary.status,events:r.events,angleRmsDeg:rms('theta')/DEG,xRmsMm:rms('pulseX')*1000,aRms:rms('a'),peakX:r.summary.peakX,peakA:r.summary.peakA,peakJ:r.summary.peakJ});
}
const nominalTrims=[];
for(const trimDeg of [0,.1,.2,.234]){
 const r=E.simulate({scenario:'balance',duration:20,initialAngle:2,sensorBias:.234*DEG,trim:trimDeg*DEG});
 const tail=r.trace.filter(x=>x.t>=15),mean=k=>tail.reduce((a,x)=>a+x[k],0)/tail.length;
 nominalTrims.push({trimDeg,status:r.summary.status,meanPulseXmm:mean('pulseX')*1000,meanTrueAngleDeg:mean('theta')/DEG});
}
const summary=[];for(const bal_pw of [6,7,8])for(const pz of [.85,1,1.1]){const cases=results.filter(x=>x.bal_pw===bal_pw&&x.pz===pz);const passed=cases.filter(x=>x.status==='balanced'&&!x.events.length);summary.push({bal_pw,pz,passed:passed.length,total:cases.length,meanAngleRms:passed.reduce((a,x)=>a+x.angleRmsDeg,0)/passed.length});}
fs.writeFileSync(path.join(__dirname,'screen.json'),JSON.stringify({note:'Unidentified tracking/lag sensitivity assumptions, not fitted physical predictions. Same angle bias +.234deg, trim +.2deg for gain grid. All limits unchanged.',summary,nominalTrims,results},null,2));console.log(JSON.stringify({summary,nominalTrims},null,2));
