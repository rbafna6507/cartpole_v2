'use strict';
// Offline comparison only. Does not connect to hardware or change defaults.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const E=require('../simulator175/engine.js');
const base={scenario:'swing',duration:30,vmax:.8,amax_s:15,amax_b:15,jmax:120,ke:2,kpx:30,kdx:.5};
const variants=[['baseline',{}],['vmax_0.6',{vmax:.6}],['kdx_1',{kdx:1}],['kdx_2',{kdx:2}],['kdx_4',{kdx:4}],['ke_3',{ke:3}],['ke_4',{ke:4}],['kpx_45',{kpx:45}],['kpx_60',{kpx:60}],['phase_soft_0.5',{phase_soft:.5}],['phase_soft_2',{phase_soft:2}],['kpx_60_vmax_0.6',{kpx:60,vmax:.6}],['kpx_60_kdx_1',{kpx:60,kdx:1}]];
const starts=[{initialAngle:0,initialX:0},{initialAngle:5,initialX:.01},{initialAngle:-5,initialX:-.01}];
const rows=[];
for(const [name,settings] of variants)for(const start of starts){
 const r=E.simulate({...base,...settings,...start});
 const maxLiftDeg=Math.max(...r.trace.map(s=>180-Math.abs(s.theta)*180/Math.PI));
 rows.push({name,start,settings:{...base,...settings},maxLiftDeg,...r.summary});
}
const hash=crypto.createHash('sha256').update(fs.readFileSync(path.join(__dirname,'../simulator175/engine.js'))).digest('hex');
const result={engine_sha256:hash,note:'Ideal tracking, measured free-decay damping. Gain comparison, not evidence of physical capture or reduced slipping. PeakX is maximum absolute offset from center, not peak-to-peak travel. Source defaults are unchanged.',rows};
fs.writeFileSync(path.join(__dirname,'compact_swingup_v22.json'),JSON.stringify(result,null,2)+'\n');
for(const r of rows)console.log(r.name,JSON.stringify(r.start),`peak=${(r.peakX*1000).toFixed(1)}mm lift=${r.maxLiftDeg.toFixed(1)}deg rail=${r.recoveries} stable=${r.longestStable.toFixed(2)}s status=${r.status}`);
