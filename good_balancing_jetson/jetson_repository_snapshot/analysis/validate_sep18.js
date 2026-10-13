const E=require('../simulator175/engine.js'),fs=require('fs'),D=require('./sep18/recorded_trials.json');
const candidates=require('./sep18/gain_search_initial.json').rows.filter(r=>r.summary.status==='balanced');
const cases=[['center',{}],['down+5',{initialAngle:5}],['down-5',{initialAngle:-5}],['cart+10mm',{initialX:.01}],['cart-10mm',{initialX:-.01}],['length118',{leff:.118,damping:.42,coulomb:.4}],['damping0.42',{damping:.42}],['damping1.2',{damping:1.2}],['lag5ms',{lagMs:5}],['delay2ms',{delayMs:2}],['offset+2',{initialAngle:2}],['tracking98%',{tracking:.98}]];
const results=[];
for(const c of candidates){const checks=cases.map(([name,variant])=>({name,variant,summary:E.simulate({...c.p,duration:40,...variant}).summary}));results.push({p:c.p,passes:checks.filter(c=>c.summary.status==='balanced').length,checks});console.log('checked',c.p,'passes',results.at(-1).passes);}
results.sort((a,b)=>b.passes-a.passes);fs.writeFileSync('analysis/sep18/gain_validation.json',JSON.stringify({cases,results},null,2));
