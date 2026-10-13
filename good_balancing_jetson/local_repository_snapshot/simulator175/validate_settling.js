'use strict';
const E=require('./engine'),fs=require('fs'),crypto=require('crypto'),assert=require('node:assert/strict');
const search=require('./search_settling_results.json'),best=search.results[0];
const parameters={...E.defaults,...best.p,duration:60};
function check(variant){
 const r=E.simulate({...parameters,...variant}),tail=r.trace.filter(x=>x.t>=r.summary.duration-5);
 let lastOutside=0;
 for(const x of r.trace)if(x.mode!=='balance'||Math.abs(x.theta)>2*Math.PI/180||Math.abs(x.x)>.01||Math.abs(x.actualV)>.02)lastOutside=x.t;
 const rms=k=>Math.sqrt(tail.reduce((sum,x)=>sum+x[k]**2,0)/tail.length);
 return {variant,summary:r.summary,tightSettlingTimeS:lastOutside<r.summary.duration-5?lastOutside+.01:null,finalFiveSeconds:{angleRmsDeg:rms('theta')*180/Math.PI,positionRmsMm:rms('x')*1000,velocityRmsMps:rms('actualV')}};
}
const screened=[{},...search.calibration,...search.stress].map(check);
for(const c of screened){assert.equal(c.summary.status,'balanced');assert.ok(c.summary.peakX<.14);assert.ok(c.summary.peakV<=.552);assert.ok(c.summary.peakA<=5+1e-6);assert.ok(c.summary.peakJ<=25+1e-6);}
const extended=[{integrationDt:.0005},{initialX:.01},{initialX:-.01},{initialAngle:2},{initialAngle:-2},{lagMs:10},{tracking:.95},{leff:.163,damping:.48,lagMs:5,initialX:.005}].map(check);
assert.equal(extended[0].summary.status,'balanced');
const evidence={schema:1,engineSha256:crypto.createHash('sha256').update(fs.readFileSync(__dirname+'/engine.js')).digest('hex'),parameters,search:{seed:search.seed,candidates:search.tested,nominalSettled:search.nominal,allThreeFitsSettled:search.calibrated},screened,extended,hardware:{physicalMotorVerified:false,pulleyRadiusM:.12/(2*Math.PI),motorSpeedAtCapRpm:parameters.vmax/.12*60,stepRateAtCapHz:parameters.vmax*parameters.stepsPerM,illustrativeMovingMassKg:.5,translationalTorqueAtSwingCapNm:.5*parameters.amax_s*.12/(2*Math.PI),translationalTorqueAtBrakingCapNm:.5*parameters.amax_b*.12/(2*Math.PI),torqueNote:'Translational inertia only; excludes drag, pendulum reaction, rotor/pulley inertia and efficiency. Mass is an assumption, not measured.'}};
fs.writeFileSync(__dirname+'/settling_validation.json',JSON.stringify(evidence,null,2));
fs.writeFileSync(__dirname+'/presets.js','/* Simulation candidates, not hardware-validated motor limits. */\nwindow.PENDULUM_PRESETS = '+JSON.stringify({settling:{name:'Settling candidate · 3 / 5 · j25 · v0.55',parameters,note:'Simulation candidate: 15/15 screening cases settled. ke = 3.5 is required. Motor capability remains unverified.'}},null,2)+';\n');
const r=E.simulate(parameters),keys=Object.keys(r.trace[0]);fs.writeFileSync(__dirname+'/settling_trace.csv',[keys.join(','),...r.trace.map(x=>keys.map(k=>x[k]).join(','))].join('\n'));
console.log(JSON.stringify({screened:screened.length,passed:screened.filter(c=>c.summary.status==='balanced').length,nominal:screened[0],extended:extended.map(c=>({variant:c.variant,status:c.summary.status})),hardware:evidence.hardware},null,2));
