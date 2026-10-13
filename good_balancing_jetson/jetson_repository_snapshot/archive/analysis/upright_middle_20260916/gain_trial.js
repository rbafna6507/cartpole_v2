'use strict';
const E=require('../../simulator175/engine'),fs=require('fs'),path=require('path');
const results=[];
for(const bal_pw of [7,8])for(const lagMs of [0,20,40,60])for(const tracking of [.6,.8,1]){
 const r=E.simulate({scenario:'balance',duration:20,initialAngle:2,bal_pw,lagMs,tracking});const tail=r.trace.filter(x=>x.t>=15);const rms=k=>Math.sqrt(tail.reduce((a,x)=>a+x[k]**2,0)/tail.length);
 results.push({bal_pw,lagMs,tracking,status:r.summary.status,events:r.events,angleRmsDeg:rms('theta')*180/Math.PI,accelRms:rms('a'),peakX:r.summary.peakX});
}
fs.writeFileSync(path.join(__dirname,'gain_trial.json'),JSON.stringify({note:'Production simulator, unchanged motion limits and no angle trim. Lag/tracking are sensitivity assumptions, not identified physical values.',results},null,2));
for(const pw of [7,8]){const r=results.filter(x=>x.bal_pw===pw);console.log(pw,r.filter(x=>x.status==='balanced'&&!x.events.length).length,'of',r.length,'40ms ideal tracking',r.find(x=>x.lagMs===40&&x.tracking===1));}
