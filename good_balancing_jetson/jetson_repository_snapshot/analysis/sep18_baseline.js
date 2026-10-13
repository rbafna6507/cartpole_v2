const E=require('../simulator175/engine.js'),D=require('./sep18/recorded_trials.json');
for(const tr of D.trials){const p={...tr.params,duration:tr.summary.duration_s,controllerLength:tr.params.leff,leff:E.defaults.leff,initialAngle:tr.initialAngle,initialX:tr.initialX,initialOmega:tr.initialOmega,encoderMs:1};const r=E.simulate(p);console.log(tr.name,r.summary);}
for(const rail of [.093,.1,.15]){const p={ke:8.05,kpx:148,kdx:4.42,phase_soft:.2,vmax:.69,amax_s:12,amax_b:12,jmax:60,rail,duration:30,encoderMs:1};console.log('intended',rail,E.simulate(p).summary);}
