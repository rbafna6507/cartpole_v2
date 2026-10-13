const fs=require('fs'),crypto=require('crypto'),E=require('../simulator175/engine'),Old=require('./v7_sim_reference'),D=require('./data_informed_cases.json');
const fixed={vmax:.75,amax_s:15,amax_b:15,jmax:50,stepsPerM:80000};
function run(engine,p,lagMs=0){return D.capture_seeds.map(seed=>{const r=engine.simulate({...fixed,...p,...seed,lagMs,scenario:'balance',duration:6});return {trial:seed.trial,board_ms:seed.board_ms,settled:r.summary.finalStable>2,finalStable:r.summary.finalStable,fault:r.summary.fault};});}
function summary(cases){return {training:cases.filter(c=>c.trial===3&&c.settled).length,training_n:16,comparison:cases.filter(c=>c.trial!==3&&c.settled).length,comparison_n:15,faults:cases.filter(c=>c.fault).length};}
const label=require('../cartpole_controller_config.json').controller_defaults.firmware_id;
const runs={v7_recorded_limits:run(Old,{}),[label+'_recorded_limits']:run(E,{}),[label+'_new_defaults']:run(E,E.defaults),[label+'_new_defaults_assumed_10ms_lag']:run(E,E.defaults,10)};
const results={note:'Six-second balance recoveries initialized at recorded first-BALANCE telemetry states. Settled means final continuous stable interval >2 s, not hardware success. Inputs are approximate states; none of these physical attempts held balance.',source:D.source,source_snapshot_sha256:D.snapshot_sha256,engine_sha256:crypto.createHash('sha256').update(fs.readFileSync(__dirname+'/../simulator175/engine.js')).digest('hex'),summaries:Object.fromEntries(Object.entries(runs).map(([k,v])=>[k,summary(v)])),runs};
fs.writeFileSync(__dirname+'/recorded_validation.json',JSON.stringify(results,null,2));
console.log(results.summaries);
