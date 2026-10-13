'use strict';
const E=window.PendulumSim,D=window.PENDULUM_DATA,$=id=>document.getElementById(id);
const colors=['#78dfd0','#ecb675','#a9adff','#e699bd'];
const candidates=window.PENDULUM_PRESETS||{};
for(const [key,preset] of Object.entries(candidates))$('preset').add(new Option(preset.name,key));
const numeric=Object.keys(E.defaults).filter(k=>$(k)?.type==='number');
const cd=D.controller.controller_defaults, hw=D.controller.hardware, logged=D.control_log.params;
const baseline={...E.defaults,physicalLength:.175,leff:D.fit.selected_effective_length_m,damping:D.fit.equivalent_viscous_decay_per_s,
  amax_s:logged.amax_s,amax_b:logged.amax_b,
  jmax:logged.jmax,vmax:logged.vmax,rail:logged.rail,
  catch_a:logged.catch_a,catch_r:logged.catch_r,giveup:logged.giveup,
  pulleyTeeth:20,stepsPerM:logged.cart_steps_per_m,encoderMs:D.configuration.calibration_snapshot.encoder.average_sample_interval_ms,
  bw:logged.bw,ke:logged.ke,kpx:logged.kpx,kdx:logged.kdx,
  controllerLength:D.fit.firmware_effective_length_m};
let formDefaults={...baseline};
let experiments=[],selected=null,nextId=1,playing=true,playTime=0,lastFrame=0,activeTab='simulation';
for(const [value,text] of Object.entries(E.styles))$('style').add(new Option(text,value));
for(const [i,c] of D.captures.entries())$('capture').add(new Option(` ${c.physical_length_mm} mm · ${c.name.slice(-6).replace(/(..)(..)(..)/,'$1:$2:$3')}`,i));
function read(){const p={...formDefaults,scenario:$('scenario').value,style:$('style').value};for(const k of numeric)p[k]=Number($(k).value);p.stepsPerM=200*Number($('microsteps').value)/(p.pulleyTeeth*.002);return E.parameters(p);}
function set(p){p={...E.defaults,...p};formDefaults=p;for(const k of numeric)$(k).value=p[k];$('style').value=p.style;$('scenario').value=p.scenario;$('microsteps').value=String(Math.round(p.stepsPerM*(p.pulleyTeeth*.002)/200));styleNote();}
function styleNote(){const s=$('style').value;$('styleNote').textContent={jerk:'Firmware motion governor: 1 kHz acceleration updates, jerk-limited ramps, DDS pulse counting.',trapezoid:'Instant acceleration changes with speed and rail guarding. Jerk is measured but not constrained.',velocity:'Velocity targets arrive at the command interval; an inner jerk-limited ramp follows them.',position:'Position targets arrive at the command interval; a proportional position loop requests velocity.'}[s];$('jmax').disabled=s==='trapezoid';$('commandMs').disabled=['jerk','trapezoid'].includes(s);}
function report(error){$('error').textContent=error?.message||'';}
function safe(fn){return async()=>{try{report(null);await fn();}catch(e){report(e);console.error(e);}};}
function add(p){const r=E.simulate(p,selectedRecording());r.id=nextId++;r.color=colors[(r.id-1)%colors.length];experiments.push(r);selected=r;playTime=0;playing=true;return r;}
function run(){add(read());render();}
function series(r,key,scale=1,dashed=false){return {name:`#${r.id}`,color:r.color,dashed,points:r.trace.map(p=>[p.t,p[key]*scale])};}
function size(id){const c=$(id),rect=c.getBoundingClientRect(),ratio=window.devicePixelRatio||1;const w=Math.max(100,rect.width),h=Math.max(100,rect.height);if(c.width!==Math.round(w*ratio)||c.height!==Math.round(h*ratio)){c.width=Math.round(w*ratio);c.height=Math.round(h*ratio);}const ctx=c.getContext('2d');ctx.setTransform(ratio,0,0,ratio,0,0);ctx.clearRect(0,0,w,h);return {ctx,w,h};}
function chart(id,ss,{min,max,guides=[],wrap=false}={}){
  if(!$(id).getBoundingClientRect().width)return;
  const {ctx:c,w,h}=size(id),left=49,right=15,top=18,bottom=28;
  const points=ss.flatMap(s=>s.points),last=Math.max(1,...points.map(p=>p[0]));
  let lo=min??Math.min(0,...points.map(p=>p[1])),hi=max??Math.max(0,...points.map(p=>p[1]));
  if(min===undefined){const pad=Math.max(.001,(hi-lo)*.12);lo-=pad;hi+=pad;}
  const X=t=>left+t/last*(w-left-right),Y=v=>h-bottom-(v-lo)/(hi-lo)*(h-top-bottom);
  c.font='10px ui-monospace,monospace';c.lineWidth=1;
  for(let i=0;i<=4;i++){
    const value=lo+(hi-lo)*i/4,y=Y(value);c.strokeStyle='#334247';c.beginPath();c.moveTo(left,y);c.lineTo(w-right,y);c.stroke();c.fillStyle='#98abad';c.textAlign='right';c.fillText(Math.abs(value)>=100?value.toFixed(0):Math.abs(hi-lo)<1?value.toFixed(3):value.toFixed(1),left-7,y+3);
    c.textAlign='center';c.fillText(`${(last*i/4).toFixed(last>10?0:1)}s`,X(last*i/4),h-7);
  }
  c.save();c.beginPath();c.rect(left,top,w-left-right,h-top-bottom);c.clip();
  for(const v of guides){c.strokeStyle='#aa7868';c.setLineDash([4,4]);c.beginPath();c.moveTo(left,Y(v));c.lineTo(w-right,Y(v));c.stroke();}c.setLineDash([]);
  for(const s of ss){c.strokeStyle=s.color;c.lineWidth=1.65;c.setLineDash(s.dashed?[4,4]:[]);c.beginPath();let prev=null;for(const [t,v] of s.points){if(prev===null||(wrap&&Math.abs(v-prev)>180))c.moveTo(X(t),Y(v));else c.lineTo(X(t),Y(v));prev=v;}c.stroke();}c.restore();c.setLineDash([]);
  c.textAlign='left';c.font='9px ui-monospace';let lx=left;for(const s of ss.filter(s=>!s.dashed)){c.fillStyle=s.color;c.fillText(s.name,lx,10);lx+=c.measureText(s.name).width+16;}
}
function render(){
  if(!selected)return;
  const s=selected.summary,p=selected.parameters;
  if(!$('terminalCommands').hidden)$('terminalCommands').textContent=E.consoleCommands(p);
  const outcome=s.fault||{balanced:'Balanced','not settled':'Not settled',complete:'Complete'}[s.status];
  const m=[['Outcome',outcome,s.fault?'Simulation stopped at fault':`${s.catches} captures · ${s.finalStable.toFixed(1)} s final stable`],
    ['Peak cart travel',`${(s.peakX*1000).toFixed(1)} mm`,`${(p.rail*1000).toFixed(0)} mm physical half travel`],
    ['Peak command speed',`${s.peakV.toFixed(2)} m/s`,`${(s.peakHz/1000).toFixed(1)} kHz STEP rate`],
    ['Peak command jerk',`${s.peakJ.toFixed(0)} m/s³`,`${s.brakingSeconds.toFixed(2)} s rail braking`]];
  $('metrics').replaceChildren(...m.map(([label,value,detail],i)=>{const el=document.createElement('div');el.className='metric';const a=document.createElement('span');a.className='label';a.textContent=label;const b=document.createElement('span');b.className='value'+(i===0?(s.status==='balanced'?' good':' warn'):'');b.style.fontSize=i===0&&value.length>15?'17px':'';b.textContent=value;const d=document.createElement('span');d.className='detail';d.textContent=detail;el.append(a,b,d);return el;}));
  const visible=[...experiments.filter(r=>r!==selected).slice(-3),selected];
  chart('angleChart',visible.map(r=>series(r,'theta',180/Math.PI)),{min:-180,max:180,wrap:true});
  chart('positionChart',visible.flatMap(r=>[series(r,'x',1000),series(r,'pulseX',1000,true)]),{min:-p.rail*1000,max:p.rail*1000,guides:[-(p.rail-.015)*1000,(p.rail-.015)*1000]});
  chart('velocityChart',visible.map(r=>series(r,'v')),{guides:[-p.vmax,p.vmax]});
  chart('accelChart',visible.flatMap(r=>[series(r,'a'),...(r.parameters.tracking!==1||r.parameters.lagMs>0?[series(r,'actualA',1,true)]:[])]));
  chart('jerkChart',visible.map(r=>series(r,'jerk')));
  chart('pulseChart',visible.map(r=>series(r,'hz',.001)),{guides:[p.pulseMax*.001]});
  $('runs').replaceChildren(...experiments.map(r=>{const tr=document.createElement('tr'),s=r.summary,p=r.parameters;tr.className=r===selected?'selected':'';
    const vals=[`#${r.id} ${p.style} / ${p.scenario}`,s.fault||s.status,`${p.amax_s} / ${p.amax_b}`,p.style==='trapezoid'?'off':p.jmax,p.vmax,(s.peakX*1000).toFixed(1),s.peakV.toFixed(3),s.peakJ.toFixed(0),s.peakHz.toFixed(0),s.finalStable.toFixed(1)];
    for(const [i,v] of vals.entries()){const td=document.createElement('td');td.textContent=v;if(i===0){const dot=document.createElement('span');dot.className='swatch';dot.style.background=r.color;td.prepend(dot);}tr.append(td);}tr.tabIndex=0;tr.setAttribute('aria-label',`Inspect experiment ${r.id}`);const choose=()=>{selected=r;playTime=0;set(p);render();};tr.onclick=choose;tr.onkeydown=e=>{if(e.key==='Enter')choose();};return tr;}));
  $('playLabel').textContent=`Experiment #${selected.id} · ${p.style} · ${s.duration.toFixed(1)} s`;
}
function scene(){if(!selected||activeTab!=='simulation')return;const trace=selected.trace,p=selected.parameters;
  const row=trace[Math.min(trace.length-1,Math.round(playTime/.01))],{ctx:c,w,h}=size('scene');
  const scale=Math.min((w-80)/(2*p.rail+.15),(h-60)/.35,500),y=h*.5+15,cx=w/2+row.x*scale,cy=y-15,L=p.physicalLength*scale;
  c.strokeStyle='#455c60';c.lineWidth=3;c.beginPath();c.moveTo(w/2-p.rail*scale,y);c.lineTo(w/2+p.rail*scale,y);c.stroke();
  for(const sign of [-1,1]){const xx=w/2+sign*p.rail*scale;c.fillStyle='#a57469';c.fillRect(xx-3,y-14,6,28);c.font='10px ui-monospace';c.textAlign='center';c.fillStyle='#97afb2';c.fillText(`${sign*p.rail*1000} mm`,xx,y+34);}
  c.strokeStyle='#456368';c.setLineDash([3,5]);c.lineWidth=1;c.beginPath();c.moveTo(w/2,20);c.lineTo(w/2,y+14);c.stroke();c.setLineDash([]);
  c.strokeStyle='#ecb675';c.strokeRect(w/2+row.pulseX*scale-19,cy-8,38,17);
  c.fillStyle='#78dfd0';c.fillRect(cx-17,cy-7,34,14);c.strokeStyle='#d0eeea';c.lineWidth=3;c.beginPath();c.moveTo(cx,cy);c.lineTo(cx+Math.sin(row.theta)*L,cy-Math.cos(row.theta)*L);c.stroke();c.fillStyle='#ecb675';c.beginPath();c.arc(cx+Math.sin(row.theta)*L,cy-Math.cos(row.theta)*L,6,0,2*Math.PI);c.fill();
  c.font='10px ui-monospace';c.fillStyle='#9db8ba';c.textAlign='left';c.fillText(`${row.mode.toUpperCase()}${row.braking?' / RAIL BRAKING':''}`,8,15);c.fillText('Solid cart: modeled physical motion · outline: pulse position',8,h-4);
  $('clock').textContent=`${row.t.toFixed(2)} s`;$('scrub').value=1000*playTime/Math.max(.01,selected.summary.duration);$('play').textContent=playing?'Pause':'Play';
}
function frame(now){const delta=lastFrame?Math.min(.1,(now-lastFrame)/1000):0;lastFrame=now;if(selected&&playing&&activeTab==='simulation'){playTime+=delta;if(playTime>selected.summary.duration){playTime=selected.summary.duration;playing=false;}}scene();requestAnimationFrame(frame);}
function calibration(){const p=read(),cap=D.captures[Number($('capture').value)],fit=E.decay(cap,p);
  $('calInfo').textContent=`${cap.physical_length_mm} mm capture · ${cap.cycle_count} selected cycles · period ${cap.period_s.toFixed(4)} s · effective length ${(cap.length_m*1000).toFixed(2)} mm. Current plant overlay: ${fit.rmseDeg.toFixed(2)}° angle RMSE over five seconds, starting at ${cap.start_s.toFixed(2)} s in the capture.`;
  chart('decayChart',[{name:'Measured',color:colors[0],points:fit.points.map(x=>[x.t,x.observed*180/Math.PI])},{name:'Current plant',color:colors[1],points:fit.points.map(x=>[x.t,x.predicted*180/Math.PI])}]);
  chart('fullDecay',D.captures.map((c,i)=>({name:`Run 0${i+1}`,color:colors[i],points:c.full.map(([t,q])=>[t,q*180/Math.PI])})));
}
function selectedRecording(){
  const i=Number($('recordingSelect').value);
  if($('recordingSelect').value==='archive')return D.control_log;
  const tr=D.latest_run.trials[i];
  return {...tr,firmware:'v25 · '+tr.name,source:D.latest_run.source,sha256:D.latest_run.sha256,events_source:D.latest_run.events_source,events_sha256:D.latest_run.events_sha256,
    points:tr.points.map(p=>[p[0],E.wrap(p[1]-Math.PI),p[3],p[4],p[5]])};
}
function recording(){const l=selectedRecording(),s=l.summary;$('logInfo').textContent=`${l.firmware} · ${s.samples.toLocaleString()} active samples over ${s.duration_s.toFixed(1)} s. Encoder excursion from hanging reached ${s.max_angle_from_down_deg.toFixed(1)}°. Pulse position reached ${(s.max_pulse_position_m*1000).toFixed(1)} mm; command speed reached ${s.max_command_speed_m_s.toFixed(2)} m/s. ${s.balance_entries} balance entries; longest ${(s.longest_balance_s||0).toFixed(3)} s. ${s.rail_fraction===undefined?'':`Rail recovery ${(100*s.rail_fraction).toFixed(1)}%. `}${s.outcome||''}`;
  chart('logAngle',[{name:'Measured angle from hanging (°)',color:colors[0],points:l.points.map(p=>[p[0],p[1]*180/Math.PI])}],{min:-180,max:180,wrap:true});
  chart('logPosition',[{name:'Pulse-inferred cart position (mm)',color:colors[1],points:l.points.map(p=>[p[0],p[2]*1000])}],{min:-l.params.rail*1000,max:l.params.rail*1000,guides:[-(l.params.rail-.015)*1000,(l.params.rail-.015)*1000]});
  $('logParams').textContent=JSON.stringify({source:l.source,sha256:l.sha256,events_source:l.events_source,firmware:l.firmware,parameters:l.params},null,2);
}
function tab(name){activeTab=name;for(const e of document.querySelectorAll('.tabpage'))e.hidden=e.id!==name;for(const b of document.querySelectorAll('[data-tab]'))b.classList.toggle('active',b.dataset.tab===name);if(name==='calibration')calibration();else if(name==='recording')recording();else render();}
function download(filename,content,type){const url=URL.createObjectURL(new Blob([content],{type})),a=document.createElement('a');a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
async function batch(params){$('busy').textContent='Running…';const buttons=[...document.querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);try{for(const [i,p] of params.entries()){add(p);$('busy').textContent=`${i+1} / ${params.length} experiments`;await new Promise(requestAnimationFrame);}render();}finally{buttons.forEach(b=>b.disabled=false);$('busy').textContent='Ready';}}
$('preset').onchange=()=>{const key=$('preset').value;set(candidates[key]?.parameters||(key==='current'?{...E.defaults,physicalLength:D.controller.current_pendulum.physical_length_mm/1000,leff:D.controller.measured_pendulum.effective_length_m,controllerLength:cd.effective_length_m,damping:D.controller.current_pendulum.simulation_damping_per_s,pulleyTeeth:hw.pulley_teeth,stepsPerM:hw.cart_steps_per_mm*1000,amax_s:cd.swing_max_acceleration_m_per_s2,amax_b:cd.balance_max_acceleration_m_per_s2,jmax:cd.max_cart_jerk_m_per_s3,vmax:cd.max_cart_speed_m_per_s,vmax_s:cd.swing_max_speed_m_per_s,vmax_b:cd.balance_max_speed_m_per_s,catch_a:cd.catch_angle_rad,catch_r:cd.catch_rate_rad_per_s,giveup:cd.giveup_angle_rad}:baseline));$('presetNote').textContent=candidates[key]?.note||(key==='current'?'v26: separate speed limits, gradual approach to balance, and capture forecast with jerk and rail constraints. Prepared for testing; hardware performance is unverified.':'Historical 175 mm recording.');};
$('run').onclick=safe(run);$('style').onchange=styleNote;
$('scenario').onchange=()=>{if($('scenario').value==='balance'&&Number($('initialAngle').value)===0)$('initialAngle').value=5;else if($('scenario').value==='decay')$('initialAngle').value=15;};
$('compare').onclick=safe(()=>{const p=read();return batch(Object.keys(E.styles).map(style=>({...p,style})));});
$('sweep').onclick=safe(()=>{const p=read();const parse=id=>$(id).value.split(',').map(s=>{if(!s.trim())throw Error('Sweep values must be numbers');const n=Number(s);if(!Number.isFinite(n))throw Error('Sweep values must be numbers');return n;});const a=parse('sweepA'),j=parse('sweepJ'),v=parse('sweepV');if(a.length*j.length*v.length>64)throw Error('Use at most 64 sweep combinations');const all=[];for(const av of a)for(const jv of j)for(const vv of v)all.push(E.parameters({...p,amax_s:av,amax_b:av,jmax:jv,vmax:vv}));return batch(all);});
$('reset').onclick=safe(()=>{$('preset').value='recorded';$('presetNote').textContent='';set(baseline);run();});$('clear').onclick=()=>{experiments=[selected];render();};
$('play').onclick=()=>{if(playTime>=selected.summary.duration)playTime=0;playing=!playing;};$('scrub').oninput=()=>{playing=false;playTime=Number($('scrub').value)/1000*selected.summary.duration;scene();};
$('capture').onchange=safe(calibration);$('refreshCalibration').onclick=safe(calibration);
$('exportCommands').onclick=()=>{const p=selected.parameters;$('terminalCommands').hidden=false;$('terminalCommands').textContent=E.consoleCommands(p);download('pendulum-commands.txt',E.consoleCommands(p)+'\n','text/plain');};
$('recordingSelect').onchange=safe(recording);
$('replay').onclick=safe(()=>{$('scenario').value='replay';$('duration').value=Math.min(120,selectedRecording().summary.duration_s);tab('simulation');run();});
$('exportCsv').onclick=()=>{const keys=Object.keys(selected.trace[0]);download(`pendulum-experiment-${selected.id}.csv`,[keys.join(','),...selected.trace.map(p=>keys.map(k=>p[k]).join(','))].join('\n'),'text/csv');};
$('exportJson').onclick=()=>download('pendulum-experiments.json',JSON.stringify({schema:1,sources:D.sources,calibrationSources:D.captures.map(({source,sha256})=>({source,sha256})),controlLog:{source:selectedRecording().source,sha256:selectedRecording().sha256,events_sha256:selectedRecording().events_sha256},latestRun:{source:D.latest_run.source,sha256:D.latest_run.sha256,events_sha256:D.latest_run.events_sha256},assumptions:'Acceleration-driven nonlinear pendulum; assumed motor tracking, no calibrated torque model.',experiments},null,2),'application/json');
for(const b of document.querySelectorAll('[data-tab]'))b.onclick=safe(()=>tab(b.dataset.tab));
window.addEventListener('resize',()=>{if(activeTab==='simulation')render();else if(activeTab==='calibration')calibration();else recording();});
for(const [i,tr] of D.latest_run.trials.entries())$('recordingSelect').add(new Option(tr.name,String(i)));
$('recordingSelect').value='0';
$('fitSummary').textContent=`125 mm fit: ${(D.current_fit.selected_effective_length_m*1000).toFixed(2)} mm effective · ${D.current_fit.period_s.toFixed(3)} s period`;
$('sources').replaceChildren(...D.captures.map((c,i)=>{const el=document.createElement('div');el.className='cal-source';const a=document.createElement('a');a.href='../'+c.source;a.textContent=`${c.physical_length_mm} mm · ${c.name} ↗`;const desc=document.createElement('div');desc.textContent=`${c.cycle_count} cycles · ${c.period_s.toFixed(4)} s · ${(c.length_m*1000).toFixed(2)} mm · damping ${c.damping.toFixed(3)} s⁻¹`;const hash=document.createElement('code');hash.textContent=`SHA-256 ${c.sha256}`;el.append(a,desc,hash);return el;}));
$('preset').options[1].textContent=`Current ${cd.firmware_id} · jmax ${cd.max_cart_jerk_m_per_s3} · vmax ${cd.max_cart_speed_m_per_s}`;
const initialPreset=new URLSearchParams(location.search).get('preset');
if(candidates[initialPreset]){$('preset').value=initialPreset;set(candidates[initialPreset].parameters);$('presetNote').textContent=candidates[initialPreset].note;}else {$('preset').value='current';$('preset').onchange();}
run();requestAnimationFrame(frame);
