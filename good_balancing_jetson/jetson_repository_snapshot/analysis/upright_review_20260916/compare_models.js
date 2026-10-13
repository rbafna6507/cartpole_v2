'use strict';
// Isolated hypothesis experiments; does not modify the firmware or production simulator.
const fs=require('fs'),vm=require('vm'),path=require('path');
const root=path.resolve(__dirname,'../..'),R=require('./review.json');
let source=fs.readFileSync(path.join(root,'simulator175/engine.js'),'utf8');
const old='-a*Math.cos(angle)';if(!source.includes(old))throw Error('Plant equation changed');
source=source.replace(old,'-(p.accelPolarity??1)*a*Math.cos(angle)');
source=source.replace('hat=q,rate=p.initialOmega,measured=q','hat=wrap(q+(p.sensorBias||0)),rate=p.initialOmega,measured=wrap(q+(p.sensorBias||0))');
source=source.replace('Math.round(q*4096/(2*PI))','Math.round((q+(p.sensorBias||0))*4096/(2*PI))');
const context={module:{exports:{}}};vm.runInNewContext(source,context);const E=context.module.exports;
const results=[];
for(const trial of R.trials)for(const polarity of [1,-1])for(const offset of [0,R.hanging_reference.implied_vertical_offset_deg]){
 const p={scenario:'balance',duration:10,bal_pw:8,initialAngle:trial.pre_start_angle_deg-offset,initialOmega:trial.pre_start_rate,initialX:trial.pre_start_x_mm/1000,accelPolarity:polarity,sensorBias:offset*Math.PI/180};
 const r=E.simulate(p);results.push({trial:trial.trial,polarity,offsetDeg:offset,status:r.summary.status,firstEvent:r.events[0]||null,peakXmm:r.summary.peakX*1000,peakA:r.summary.peakA});
}
const output={note:'Hypothesis comparison, not a fitted or validated plant. Same sampled pre-start states; hand contact/release and actual motor response unknown.',results};fs.writeFileSync(path.join(__dirname,'model_comparison.json'),JSON.stringify(output,null,2));
for(const polarity of [1,-1])for(const offset of [0,R.hanging_reference.implied_vertical_offset_deg]){
 const cases=results.filter(r=>r.polarity===polarity&&r.offsetDeg===offset);console.log({polarity,offsetDeg:offset,balanced:cases.filter(r=>r.status==='balanced').length,firstAbort:cases.map(r=>r.firstEvent?.t??null)});
}
const baseline=require(path.join(root,'simulator175/engine.js')),screen=[];
for(const L of [.1657755677,.225,.25,.3])for(const ke of [1,2,3,4,5,6,8]){
 const r=baseline.simulate({scenario:'swing',duration:25,leff:L,controllerLength:L,ke});
 screen.push({effectiveLength:L,energyGain:ke,status:r.summary.status,firstCatch:r.summary.firstCatch,stable:r.summary.finalStable,peakX:r.summary.peakX,fault:r.summary.fault});
}
fs.writeFileSync(path.join(__dirname,'length_swing_screen.json'),JSON.stringify({note:'Ideal acceleration tracking; friction retained by assumption, controller length retuned. This tests theoretical compatibility, not physical motor capability or a proposed mass distribution.',results:screen},null,2));
