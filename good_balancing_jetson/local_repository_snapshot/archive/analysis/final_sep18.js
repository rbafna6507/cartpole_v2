const E=require('../simulator175/engine.js'),fs=require('fs'),crypto=require('crypto');
const fit=require('./sep18/decay_fit.json')[0].parameters;
const recent={leff:fit.leff,damping:fit.damping,coulomb:fit.coulomb};
const cases=[['old fit / centered',{}],['old fit / +5deg',{initialAngle:5}],['old fit / -5deg',{initialAngle:-5}],['old fit / x+10mm',{initialX:.01}],['old fit / x-10mm',{initialX:-.01}],['recent fit / centered',{...recent}],['recent fit / +5deg',{...recent,initialAngle:5}],['recent fit / -5deg',{...recent,initialAngle:-5}],['recent fit / x+10mm',{...recent,initialX:.01}],['recent fit / x-10mm',{...recent,initialX:-.01}],['old fit / lag5ms',{lagMs:5}],['old fit / delay2ms',{delayMs:2}],['old fit / encoder+2deg',{encoderOffsetDeg:2}],['old fit / encoder-2deg',{encoderOffsetDeg:-2}],['recent fit / damping .25',{...recent,damping:.25}],['recent fit / damping .6',{...recent,damping:.6}],['recent fit / friction .45',{...recent,coulomb:.45}],['old fit / tracking98%',{tracking:.98}]];
const cand=require('./sep18/gain_refinement.json').rows.slice(0,6).map(r=>r.p);
cand.push({ke:8,kpx:150,kdx:4.4,phase_soft:.2,pw:7,vmax:.8,amax_s:12,amax_b:12,jmax:60,rail:.15});
const results=[];
for(const p of cand){const checks=cases.map(([name,variant])=>({name,variant,summary:E.simulate({...p,duration:60,...variant}).summary}));const row={p,passes:checks.filter(c=>c.summary.status==='balanced').length,checks};results.push(row);console.log(JSON.stringify({p,passes:row.passes,failures:checks.filter(c=>c.summary.status!=='balanced').map(c=>c.name)}));}
results.sort((a,b)=>b.passes-a.passes||b.checks.reduce((s,r)=>s+r.summary.finalStable,0)-a.checks.reduce((s,r)=>s+r.summary.finalStable,0));
const data={engine_sha256:crypto.createHash('sha256').update(fs.readFileSync('simulator175/engine.js')).digest('hex'),duration_s:60,case_count:cases.length,recent_plant:recent,results};
fs.writeFileSync('analysis/sep18/final_validation.json',JSON.stringify(data,null,2));
