const fs=require('fs'),crypto=require('crypto');
const E=require('../simulator175/engine'),B=require('./v26/v25_engine');
const data=require('./sep18/final_validation.json'),cases=data.results[0].checks;
const p={...data.results[0].p,duration:60,vmax_s:.8,vmax_b:.8,approach_angle:.8,approach_v:.3,catch_v:.3,catch_da:4};
const checks=cases.map(c=>({name:c.name,variant:c.variant,before:B.simulate({...p,...c.variant}).summary,after:E.simulate({...p,...c.variant}).summary}));
const out={parameters:p,engine_sha256:crypto.createHash('sha256').update(fs.readFileSync('simulator175/engine.js')).digest('hex'),checks,passes:{before:checks.filter(c=>c.before.status==='balanced').length,after:checks.filter(c=>c.after.status==='balanced').length}};
fs.writeFileSync('analysis/v26/validation.json',JSON.stringify(out,null,2));console.log(out.passes);console.log(checks.map(c=>[c.name,c.before.status,c.after.status,c.after.firstCatch]));
