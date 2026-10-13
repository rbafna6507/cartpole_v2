'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),cp=require('node:child_process'),os=require('node:os'),path=require('node:path');
const E=require('./engine.js');let checks=0;
function test(name,fn){fn();checks++;console.log('PASS',name);}
const ctx={window:{}};vm.runInNewContext(fs.readFileSync(path.join(__dirname,'data.js'),'utf8'),ctx);const D=ctx.window.PENDULUM_DATA;
const near=(a,b,tol=1e-8)=>assert.ok(Math.abs(a-b)<tol,`${a} != ${b} ± ${tol}`);
test('source SHA-256 matches all raw calibration captures and selected control log',()=>{
 const crypto=require('node:crypto');
 for(const s of [...D.captures,D.control_log,...D.sources]){
 const name=s.source||s.path;
 const hash=crypto.createHash('sha256').update(fs.readFileSync(path.join(__dirname,'..',name))).digest('hex');assert.equal(hash,s.sha256);}
 assert.equal(D.captures.length,6);assert.equal(D.fit.total_cycles,33);assert.equal(D.current_fit.total_cycles,20);near(E.defaults.bw,D.controller.controller_defaults.estimator_bandwidth_hz);
});
test('GUI current and recorded presets retain their own pulley geometry',()=>{
 const nodes={};const element=id=>nodes[id]||(nodes[id]={value:'',type:typeof E.defaults[id]==='number'?'number':'select',add(){}});
 const ui={window:{PendulumSim:E,PENDULUM_DATA:D},document:{getElementById:element},Option:function(){}};
 vm.createContext(ui);vm.runInContext(fs.readFileSync(path.join(__dirname,'presets.js'),'utf8'),ui);
 const app=fs.readFileSync(path.join(__dirname,'app.js'),'utf8');
 vm.runInContext(app.slice(0,app.indexOf("$('run').onclick")),ui);
 for(const [key,teeth,steps,vmax] of [['current',60,3200/.12,1.5],['recorded',20,80000,.75],['upright',60,3200/.12,1.5]]){
  element('preset').value=key;element('preset').onchange();
  const p=vm.runInContext('read()',ui);assert.equal(p.pulleyTeeth,teeth);near(p.stepsPerM,steps,.00001);near(p.vmax,vmax);near(p.leff,key==='recorded'?D.fit.selected_effective_length_m:D.current_fit.selected_effective_length_m);near(p.controllerLength,key==='recorded'?.166:.124);near(p.physicalLength,key==='recorded'?.175:.125);assert.equal(Number(element('microsteps').value),16);
 }
});
test('JavaScript motion governor matches current compiled C++ firmware header',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'pendulum-parity-'));
 try{
 const bin=path.join(dir,'reference');cp.execFileSync('clang++',['-std=c++11','-O2','-Wall','-Wextra','-Werror',path.join(__dirname,'firmware_parity.cpp'),'-o',bin]);
 const lines=cp.execFileSync(bin,{encoding:'utf8'}).trim().split('\n');
 for(const line of lines){const [tag,...rest]=line.split(' ');const v=rest.map(Number);
 if(tag==='gain')E.gains(E.defaults).forEach((x,i)=>near(x,v[i],1e-5));
 else if(tag==='upright_gain')E.gains({...E.defaults,pw:E.defaults.bal_pw}).forEach((x,i)=>near(x,v[i],1e-5));
 else if(tag==='estimate'){const [bw,m,a,r,na,nr]=v;const actual=E.estimate(m,bw,.001,a,r);near(actual[0],na,2e-6);near(actual[1],nr,.0003);}
 else if(tag==='geometry'){const [teeth,steps,vmax,amax,jerk]=v;assert.equal(teeth,E.defaults.pulleyTeeth);near(steps,E.defaults.stepsPerM,.003);near(vmax,E.defaults.vmax,1e-6);near(amax,E.defaults.amax_s);near(jerk,E.defaults.jmax);near(steps/1000,D.controller.hardware.cart_steps_per_mm,.00001);}
 else if(tag==='stop'){const [velocity,a,j,distance,target]=v;near(E.stoppingDistance(velocity,a,15,j),distance,2e-6);near(E.settledVelocityAccel(velocity,a,0,15,j,.001),target,2e-5);}
 else if(tag==='approach'){const [q,w,x,vel,a,pump,expected]=v;near(E.approach(E.defaults,q,w,x,vel,a,pump),expected,1e-4);}
 else if(tag==='capture'){const [q,w,x,velocity,a,expected]=v;assert.equal(Number(E.canCapture(E.defaults,q,w,x,velocity,a)),expected);}
 else {const [x,request,velocity,a,nv,na,brake]=v;
 const s=E.advance({v:velocity,a,brake:0},x,request,{...E.defaults,vmax:1.5,amax_s:6,amax_b:6,jmax:150},6,.001);near(s.v,nv,2e-6);near(s.a,na,2e-6);assert.equal(s.brake,brake);}}
 }finally{fs.rmSync(dir,{recursive:true,force:true});}
});
test('RK4 conserves pendulum energy without friction or cart motion',()=>{
 const p=E.parameters({damping:0}),energy=(q,w)=>.5*p.leff/9.81*w*w+Math.cos(q);let q=2,w=0;const en=energy(q,w);
 for(let i=0;i<20000;i++)[q,w]=E.integrate(q,w,0,p,.001);near(energy(q,w),en,1e-8);
});
test('free-decay small-angle period matches calibrated effective length',()=>{
 const p=E.parameters({damping:0});let q=Math.PI+.01,w=0,cross=[];
 for(let i=0;i<5000;i++){const old=E.wrap(q-Math.PI);[q,w]=E.integrate(q,w,0,p,.001);if(old>0&&E.wrap(q-Math.PI)<=0)cross.push(i*.001);}
 const periods=cross.slice(1).map((x,i)=>x-cross[i]);near(periods.reduce((a,b)=>a+b)/periods.length,2*Math.PI*Math.sqrt(p.leff/9.81),.001);
});
test('plant integration converges at half step over a driven trajectory',()=>{
 let q=2.8,w=1,q2=q,w2=w;const p=E.parameters(),p2=E.parameters({integrationDt:.0005});
 for(let i=0;i<10000;i++){const a=2*Math.sin(i*.001*4);[q,w]=E.integrate(q,w,a,p,.001);[q2,w2]=E.integrate(q2,w2,a,p2,.001);}
 near(q,q2,1e-6);near(w,w2,1e-5);
});
test('all styles enforce acceleration/speed/pulse limits across a limit grid',()=>{
 for(const style of Object.keys(E.styles))for(const amax of [2,6,10])for(const vmax of [.3,1.5]){
 const r=E.simulate({style,scenario:'reversal',amax_s:amax,amax_b:amax,vmax,manualSpeed:1,duration:5});
 assert.ok(r.summary.peakA<=amax+1e-7);assert.ok(r.summary.peakV<=vmax+.00201);assert.ok(r.summary.peakHz<=r.parameters.pulseMax);
 if(style!=='trapezoid')assert.ok(r.summary.peakJ<=r.parameters.jmax+1e-7);
 assert.ok(r.trace.every(s=>Number.isFinite(s.theta)&&Number.isFinite(s.x)));
 }
});
test('balance recovery, rail constraints, and commanded/physical separation',()=>{
 const r=E.simulate({scenario:'balance',initialAngle:5});assert.equal(r.summary.status,'balanced');assert.ok(r.summary.finalStable>15);assert.ok(r.summary.peakX<.14);
 const lag=E.simulate({scenario:'reversal',tracking:.5,lagMs:20,duration:2});assert.ok(lag.trace.some(s=>Math.abs(s.x-s.pulseX)>.01));
 const stuck=E.simulate({tracking:0});assert.equal(stuck.summary.fault,'No pendulum response');assert.equal(stuck.summary.peakX,0);
 const pulse=E.simulate({scenario:'reversal',pulseMax:50});assert.equal(pulse.summary.fault,'STEP pulse-rate ceiling');
});
test('stepper styles have materially different trajectories and jerk behavior',()=>{
 const j=E.simulate({scenario:'reversal'}),t=E.simulate({scenario:'reversal',style:'trapezoid'}),v=E.simulate({scenario:'reversal',style:'velocity'});
 assert.ok(t.summary.peakJ>j.summary.peakJ*10);assert.notDeepEqual(j.trace,v.trace);
});
test('decay overlays and recorded waveform replay remain finite',()=>{
 for(const c of D.captures){const fit=E.decay(c,{leff:c.length_m,damping:c.damping});assert.ok(fit.rmseDeg>0&&fit.rmseDeg<5);assert.ok(fit.points.length>400);}
 const r=E.simulate({scenario:'replay',duration:10},D.control_log);assert.ok(r.trace.length>50);assert.ok(r.trace.every(s=>Number.isFinite(s.theta)));
});
test('invalid values and missing replay input fail clearly',()=>{
 for(const p of [{jmax:0},{amax_s:-1},{vmax:NaN},{duration:Infinity},{leff:0},{style:'bad'},{initialX:.145}])assert.throws(()=>E.simulate(p));
 assert.throws(()=>E.simulate({scenario:'replay'}));
});
test('automatic rail recovery returns inside without seeking center',()=>{
 for(const initialX of [-.136,.136]){
  const r=E.simulate({initialX,duration:5});
  assert.equal(r.summary.fault,null);
  assert.ok(r.events.some(e=>e.event==='return inside complete'));
  assert.ok(r.trace.some(s=>s.mode==='rail_return'));
  assert.ok(r.summary.peakPulseX<.14);
  const handoff=r.events.find(e=>e.event==='return inside complete');
  assert.ok(Math.abs(handoff.v)<=.155 && Math.abs(handoff.a)<=1.5);
  const end=handoff.t;
  const after=r.trace.find(s=>s.t>=end);
  assert.ok(Math.abs(after.pulseX)>.12, 'recovery must finish near edge, not center');
 }
 const r=new E.RailRecovery();assert.ok(!r.atEdge(.134,.15));assert.ok(r.atEdge(.136,.15));
});
test('rail handoff waits for settled acceleration and speed; late stopped states can return',()=>{
 for(const sign of [-1,1]){
  const r=new E.RailRecovery();r.begin(sign*.129,.15,sign);
  assert.equal(r.update(sign*.129,{v:-sign*.304,a:-sign*11.214,brake:sign},.001),false);
  assert.equal(r.update(sign*.136,{v:0,a:0,brake:0},.001),false);assert.equal(r.phase,2);
  assert.equal(r.update(sign*.129,{v:-sign*.156,a:0,brake:0},.001),false);
  assert.equal(r.update(sign*.129,{v:-sign*.15,a:-sign*1.501,brake:0},.001),false);
  assert.equal(r.update(sign*.129,{v:-sign*.15,a:-sign*1.5,brake:0},.001),true);
  const next=E.advance({v:sign*.0002,a:0,brake:sign},sign*.137,-sign*1.5,E.defaults,12,.001);
  assert.equal(next.brake,0);assert.ok(next.a*sign<0);
 }
});
test('angular rate threshold trips immediately in either direction without a full turn',()=>{
 for(const w of [0,25,-25,30,-30,149.999,150,-149.999,-150])assert.equal(E.spinTrigger(w),false);
 for(const w of [150.001,-150.001,160,-160])assert.equal(E.spinTrigger(w),true);
});
test('rate recovery requires centered stopped cart and valid rate strictly below 10',()=>{
 const s=new E.SpinRecovery(),cart={v:0,a:0};
 const tick=(t,{x=0,omega=0,valid=true}={})=>s.update(x,cart,omega,valid,t);
 for(const omega of [10,-10,25,-25]){
  s.begin(0);assert.equal(tick(0,{omega}),false);assert.equal(s.phase,3);
  assert.equal(tick(60000000,{omega}),false);assert.equal(s.timedOut(60000000),false);
  assert.equal(tick(60000000,{omega:Math.sign(omega)*9.999}),true);
 }
 s.begin(0);assert.equal(tick(0,{valid:false}),false);assert.equal(tick(0),true);
 s.begin(0);assert.equal(tick(0,{x:.01}),false);
 cart.v=.006;assert.equal(tick(0),false);cart.v=0;
 cart.a=.101;assert.equal(tick(0),false);cart.a=0;assert.equal(tick(0),true);
 s.begin(0);tick(0,{omega:12});assert.equal(tick(60000000,{x:.01}),false);
 assert.equal(s.phase,2);assert.equal(s.timedOut(60000000),false);assert.equal(s.timedOut(70000001),true);
 s.reset();const start=0xffff0000;s.begin(start);
 assert.equal(s.timedOut((start+10000000)>>>0),false);assert.equal(s.timedOut((start+10000001)>>>0),true);
});
test('overspeed plant recovery trips immediately, centers and resumes below 10 in both directions',()=>{
 for(const initialOmega of [-40,40]){
  const r=E.simulate({initialOmega,initialX:.05,duration:30,spin_trip_rad_s:35});
  assert.equal(r.summary.fault,null);assert.ok(r.summary.spinRecoveries>=1);
  assert.equal(r.events.find(e=>e.event==='pendulum overspeed recovery').t,0);
  const end=r.events.find(e=>e.event==='spin recovery complete');assert.ok(end);
  assert.ok(Math.abs(end.omega)<10);assert.ok(Math.abs(end.x)<=.003);
  assert.ok(Math.abs(end.velocity)<=.005);assert.ok(Math.abs(end.acceleration)<=.1);
  assert.ok(r.summary.peakPulseX<.14);assert.ok(r.summary.peakJ<=E.defaults.jmax+.00001);
 }
});
test('upright trial abort is latched, signed 50deg fall centers, and rail abort never pumps',()=>{
 for(const sign of [-1,1]){
  // Start beyond trip deliberately to exercise recovery, not the hardware start gate.
  const fall=E.simulate({scenario:'balance',initialAngle:sign*51,initialX:sign*.03,duration:8});
  assert.equal(fall.events[0].event,'upright fall >50deg');
  assert.ok(fall.events.some(e=>e.event==='upright centered; stopped'));
  assert.ok(fall.trace.every(s=>!['swing','spin_wait'].includes(s.mode)));
  const end=fall.trace.at(-1);assert.equal(end.mode,'idle');assert.ok(Math.abs(end.pulseX)<=.003);assert.equal(end.v,0);
  // Seed outward cart momentum near the boundary to exercise the rail guard.
  const rail=E.simulate({scenario:'balance',initialAngle:sign*10,initialX:sign*.12,initialV:sign*.3,duration:8});
  assert.ok(rail.events.some(e=>e.event==='upright predictive rail protection'));
  assert.equal(rail.trace.at(-1).mode,'idle');assert.ok(rail.trace.every(s=>s.mode!=='swing'));assert.equal(rail.summary.fault,null);
 }
});

test('September 18 trials use acknowledged settings and preserve raw evidence',()=>{
 assert.equal(D.latest_run.trials.length,3);
 const [a,b,c]=D.latest_run.trials;assert.equal(a.params.vmax,.8);assert.equal(a.params.amax_s,14);assert.equal(a.params.jmax,70);assert.equal(b.params.jmax,60);assert.equal(c.params.rail,.1);
 assert.equal(a.params.ke,8);assert.equal(a.params.kpx,150);assert.equal(c.partial,false);
 assert.ok(c.summary.rail_fraction>.65 && c.summary.rail_fraction<.7);
 assert.equal(E.defaults.encoderMs,1);
});
test('terminal export uses valid firmware parameter names and no units or motion start',()=>{
 const text=E.consoleCommands({...E.defaults,ke:8,kpx:150,kdx:1,phase_soft:2,pw:6});
 const source=fs.readFileSync(path.join(__dirname,'../swingup/swingup.ino'),'utf8');
 assert.ok(text.startsWith('stop\n'));assert.ok(text.endsWith('\nparams'));
 for(const line of text.split('\n').slice(1,-1)){const [,key,value]=line.split(' ');assert.match(line,/^set [a-z0-9_]+ -?\d+(\.\d+)?$/);assert.ok(source.includes('"'+key+'"'));assert.ok(Number.isFinite(Number(value)));}
 assert.match(text,/set rail 0.15/);assert.match(text,/set leff 0.124/);assert.ok(!text.includes('auto'));
});
test('encoder offset affects only the observed control angle, not free plant motion',()=>{
 const a=E.simulate({scenario:'decay',duration:1,initialAngle:10,encoderOffsetDeg:0});const b=E.simulate({scenario:'decay',duration:1,initialAngle:10,encoderOffsetDeg:2});
 near(a.trace.at(-1).theta,b.trace.at(-1).theta);near(E.wrap(b.trace.at(-1).thetaHat-a.trace.at(-1).thetaHat),2*Math.PI/180,.003);
});



test('unused hard speed ceiling cannot change automatic trajectories or capture',()=>{
 for(const p of [{duration:12,vmax_s:.8,vmax_b:.8},{duration:12,vmax_s:.6,vmax_b:.8}]){
 const low=E.simulate({...p,vmax:.8}),high=E.simulate({...p,vmax:2.0});
 assert.deepEqual(low.trace,high.trace);assert.deepEqual(low.events,high.events);}
 for(const v of [.1,.29,.31,.7])assert.equal(E.canCapture({...E.defaults,vmax:.8},.1,-.2,0,v,1),E.canCapture({...E.defaults,vmax:2},.1,-.2,0,v,1));
});
test('independent mode limits slew down through jerk limiting on balance loss',()=>{
 let s={v:.7,a:3,brake:0};let x=0;const p={...E.defaults,vmax:.4,jmax:60,rail:10};
 for(let i=0;i<1000;i++){const previous=s;s=E.advance(s,x,0,p,12,.001);assert.ok(Math.abs(s.a-previous.a)<=.060001);assert.ok(s.v<.8);if(!i)assert.ok(s.v>.69);x+=s.v*.001;}
 assert.ok(s.v<=.401);
});
test('capture rejects high momentum and wrong acceleration despite a higher ceiling',()=>{
 assert.equal(E.canCapture({...E.defaults,vmax:2},.5844,.018,-.006,-.479,-.488),false);
 assert.equal(E.canCapture(E.defaults,0,0,.11,.29,2),false);
 assert.equal(E.canCapture(E.defaults,.08,-.2,0,0,1.1),true);
});

test('runtime spin thresholds reject invalid pairs and support custom trigger/resume',()=>{
 for(const p of [{spin_trip_rad_s:10},{spin_resume_rad_s:0},{spin_trip_rad_s:Infinity},{spin_resume_rad_s:150}])assert.throws(()=>E.parameters(p));
 assert.equal(E.defaults.spin_trip_rad_s,150);assert.equal(E.spinTrigger(40),false);assert.equal(E.spinTrigger(40,35),true);
 const s=new E.SpinRecovery();s.begin(0);assert.equal(s.update(0,{v:0,a:0},15,true,0,10),false);assert.equal(s.update(0,{v:0,a:0},15,true,0,20),true);
});
console.log(`${checks} test groups passed.`);
