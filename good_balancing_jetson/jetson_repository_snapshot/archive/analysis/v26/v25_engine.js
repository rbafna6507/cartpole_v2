/* Offline pendulum model; current 125 mm geometry uses the earlier free-decay captures. See README for model boundaries. */
(function(root){
'use strict';
const PI=Math.PI, G=9.81, clamp=(x,l,h)=>Math.max(l,Math.min(h,x));
const wrap=x=>Math.atan2(Math.sin(x),Math.cos(x));
const slew=(x,y,d)=>x+clamp(y-x,-d,d);
const styles={jerk:'Acceleration → jerk-limited DDS',trapezoid:'Acceleration → trapezoidal ramp',velocity:'Sampled velocity setpoints',position:'Streamed position targets'};
const defaults={duration:20, scenario:'swing',style:'jerk',amax_s:12,amax_b:12,jmax:60,vmax:.8,
  physicalLength:.125,leff:0.12445488778245432,controllerLength:.124,damping:0.9133833709022565,coulomb:0,
  rail:.15,pulleyTeeth:60,stepsPerM:200*16/.12,pulseMax:1000000/7/2,commandMs:10,positionGain:30,
  tracking:1,lagMs:0,delayMs:0,bw:10,encoderMs:1,encoderOffsetDeg:0,initialAngle:0,initialX:0,initialOmega:0,initialV:0,initialA:0,
  ke:2,kpx:30,kdx:.5,phase_soft:1,catch_a:.6,catch_r:3,giveup:.8,
  pw:7,bal_pw:8,pz:.85,pc1:-.8,pc2:-1.2,manualSpeed:.15,frequency:.5,integrationDt:.001};
function parameters(input={}){
  const p={...defaults,...input};
  const ranges={duration:[.1,120],amax_s:[.01,100],amax_b:[.01,100],jmax:[.1,100000],vmax:[.001,10],
    physicalLength:[.01,1],bal_pw:[1,20],leff:[.01,1],controllerLength:[.01,1],damping:[0,10],coulomb:[0,20],rail:[.04,2],pulleyTeeth:[1,200],stepsPerM:[100,1e7],
    pulseMax:[1,1e6],commandMs:[1,200],positionGain:[1,200],tracking:[0,1],lagMs:[0,200],delayMs:[0,100],
    bw:[.1,100],encoderMs:[1,20],encoderOffsetDeg:[-30,30],initialAngle:[-180,180],initialX:[-1,1],initialOmega:[-40,40],initialV:[-3,3],initialA:[-100,100],ke:[0,30],kpx:[0,200],kdx:[0,50],
    phase_soft:[.01,20],catch_a:[.01,1],catch_r:[.01,20],giveup:[.01,3],manualSpeed:[0,3],frequency:[.01,10],
    integrationDt:[.0001,.001]};
  for(const [key,[lo,hi]] of Object.entries(ranges))
    if(!Number.isFinite(p[key]) || p[key]<lo || p[key]>hi) throw Error(`${key} must be between ${lo} and ${hi}`);
  if(!styles[p.style])throw Error('Unknown stepper input style');
  if(!['swing','balance','sine','reversal','decay','replay'].includes(p.scenario))throw Error('Unknown scenario');
  if(Math.abs(p.initialX)>=p.rail-.01)throw Error('Initial cart position must be inside the fault boundary');
  return p;
}
function gains(p){
  const b1=2*p.pz*p.pw,b0=p.pw**2,c1=-(p.pc1+p.pc2),c0=p.pc1*p.pc2,L=p.controllerLength;
  const k3=-b0*c0*L/G,k4=-(b1*c0+b0*c1)*L/G;
  return [L*k3-G-L*(b0+b1*c1+c0),L*(k4-b1-c1),k3,k4];
}
function velocityAccel(v,target,amax,j,dt){const jd=j*dt;return Math.sign(target-v)*Math.min(amax,Math.sqrt(jd*jd+2*j*Math.abs(target-v))-jd);}
function settledVelocityAccel(v,a,target,amax,j,dt){
  const error=target-v,remaining=a*a/(2*j)+Math.abs(a)*dt;
  if(a*error>0 && Math.abs(error)<=remaining)return 0;
  return velocityAccel(v,target,amax,j,dt);
}
function stoppingDistance(v,a,amax,j){
  v=Math.max(0,v);a=clamp(a,-amax,amax);
  if(a<0 && v<a*a/(2*j)){
    const t=2*v/(-a+Math.sqrt(Math.max(0,a*a-2*j*v)));
    return Math.max(0,v*t+.5*a*t*t+j*t*t*t/6);
  }
  const peak=Math.min(amax,Math.sqrt(j*v+.5*a*a)),t1=Math.max(0,(a+peak)/j);
  const v1=v+a*t1-.5*j*t1*t1,hold=peak>0?Math.max(0,(v1-peak*peak/(2*j))/peak):0;
  const d1=v*t1+.5*a*t1*t1-j*t1*t1*t1/6,d2=v1*hold-.5*peak*hold*hold;
  const v2=v1-peak*hold,t3=peak/j;
  return Math.max(0,d1+d2+v2*t3-.5*peak*t3*t3+j*t3*t3*t3/6);
}
// Port of swingup/cart_motion.h; parity is checked against the compiled C++ header.
function advance(s,x,request,p,drive,dt){
  const brake=Math.max(p.amax_s,p.amax_b),j=p.style==='trapezoid'?1e12:p.jmax;
  const positive=Math.max(0,velocityAccel(s.v,p.vmax,brake,j,dt));
  const negative=Math.min(0,velocityAccel(s.v,-p.vmax,brake,j,dt));
  let target=clamp(clamp(request,-drive,drive),negative,positive);
  const na=slew(s.a,target,j*dt),nv=s.v+na*dt;
  let dir=s.brake;
  if(dir && Math.abs(s.v)<=.005 && Math.abs(s.a)<=.1)dir=0;
  if(!dir)for(const d of [-1,1]){
    const ov=nv*d,oa=na*d,room=p.rail-.015-d*x;
    if(room<=0 && ov<=.005 && oa<0)continue;
    if((ov>0||oa>0) && Math.max(0,ov)*dt+stoppingDistance(ov,oa,brake,j)>=room){dir=d;break;}
  }
  if(dir)target=settledVelocityAccel(s.v,s.a,0,brake,j,dt);
  const ca=slew(s.a,target,j*dt),cv=s.v+ca*dt;
  if(ca>0 && cv+ca*ca/(2*j)>=p.vmax)target=Math.min(target,0);
  if(ca<0 && cv-ca*ca/(2*j)<=-p.vmax)target=Math.max(target,0);
  const a=slew(s.a,target,j*dt);
  return {v:s.v+a*dt,a,brake:dir};
}
class RailRecovery {
  constructor(){this.reset();}
  reset(){this.phase=0;this.elapsed=0;this.side=0;this.exitBoundary=0;}
  begin(x,rail,dir=0){if(this.phase===0){this.phase=1;this.elapsed=0;this.side=dir||(x>=0?1:-1);this.exitBoundary=rail-.015-.005;}}
  atEdge(x,rail){return Math.abs(x)>=rail-.015;}
  update(x,s,dt){
    if(!this.phase)return false;
    this.elapsed+=dt;
    const stopped=Math.abs(s.v)<=.005 && Math.abs(s.a)<=.1;
    if(this.phase===1 && stopped)this.phase=2;
    const inward=s.v*this.side < -.005 || (s.v*this.side<=.005 && s.a*this.side<=0);
    const settled=Math.abs(s.v)<=.155 && Math.abs(s.a)<=1.5;
    if(this.phase===2 && inward && settled && !s.brake && Math.abs(x)<=this.exitBoundary){this.reset();return true;}
    return false;
  }
  demand(x,s,vmax,amax,jerk,dt){
    const target=this.phase===2?-this.side*Math.min(.15,vmax):0;
    return settledVelocityAccel(s.v,s.a,target,this.phase===2?Math.min(1.5,amax):amax,jerk,dt);
  }
}
const spinConfig={tripRadS:35,resumeRadS:10,timeoutUs:10000000};
const spinTrigger=omega=>Math.abs(omega)>spinConfig.tripRadS;
class SpinRecovery {
  constructor(){this.reset();}
  reset(){this.phase=0;this.phaseStart=0;}
  begin(now){if(!this.phase){this.phase=1;this.phaseStart=now;}}
  timedOut(now){return this.phase!==0 && this.phase!==3 && ((now-this.phaseStart)>>>0)>spinConfig.timeoutUs;}
  update(x,s,omega,valid,now){
    if(!this.phase)return false;
    const cartQuiet=Math.abs(s.v)<=.005 && Math.abs(s.a)<=.1,centered=Math.abs(x)<=.003 && cartQuiet;
    if(this.phase===1 && cartQuiet)this.phase=2;
    if(this.phase===2 && centered)this.phase=3;
    if(this.phase===3 && !centered){this.phase=2;this.phaseStart=now;}
    if(this.phase===3 && valid && Math.abs(omega)<spinConfig.resumeRadS){this.reset();return true;}
    return false;
  }
  demand(x,s,vmax,amax,jerk,dt){
    const target=this.phase===1?0:clamp(-3*x,-Math.min(.10,vmax),Math.min(.10,vmax));
    return velocityAccel(s.v,target,this.phase===1?amax:Math.min(.5,amax),jerk,dt);
  }
}
function canCapture(p,theta,omega,x,v,acceleration){
  const k=gains(p),demand=-(k[0]*theta+k[1]*omega+k[2]*x+k[3]*v);
  if(Math.abs(theta)>=p.catch_a || Math.abs(omega)>=p.catch_r || Math.abs(x)>=Math.min(.12,p.rail-.03) || Math.abs(v)>=.95*p.vmax || Math.abs(demand)>=p.amax_b)return false;
  if(Math.abs(theta)>.20 && theta*omega>0)return false;
  const ramp=Math.min(.10,Math.abs(demand-acceleration)/p.jmax);
  const alpha=(G*Math.sin(theta)-acceleration*Math.cos(theta))/p.controllerLength;
  return Math.abs(theta+omega*ramp+.5*alpha*ramp*ramp)<p.giveup;
}
function integrate(q,w,a,p,dt){
  const n=Math.ceil(dt/p.integrationDt),h=dt/n;
  const f=(angle,rate)=>(G*Math.sin(angle)-a*Math.cos(angle))/p.leff-p.damping*rate-p.coulomb*Math.tanh(rate/.05);
  for(let i=0;i<n;i++){
    const k1q=w,k1w=f(q,w),k2q=w+h*k1w/2,k2w=f(q+h*k1q/2,k2q);
    const k3q=w+h*k2w/2,k3w=f(q+h*k2q/2,k3q),k4q=w+h*k3w,k4w=f(q+h*k3q,k4q);
    q+=h*(k1q+2*k2q+2*k3q+k4q)/6;w+=h*(k1w+2*k2w+2*k3w+k4w)/6;
  }
  return [wrap(q),w];
}
function simulate(input={},recorded=null){
  const p=parameters(input),dt=.001,k=gains(p.scenario==='balance'?{...p,pw:p.bal_pw}:p),trace=[],events=[];
  if(p.scenario==='replay' && !recorded?.points?.length)throw Error('Recorded waveform is unavailable');
  const replay=p.scenario==='replay';
  let q=wrap((p.scenario==='balance'?0:PI)+p.initialAngle*PI/180),w=p.initialOmega,x=p.initialX,actualV=p.initialV;
  if(replay)q=wrap(recorded.points[0][1]+PI);
  let s={v:p.initialV,a:p.initialA,brake:0},hat=wrap(q+p.encoderOffsetDeg*PI/180),rate=p.initialOmega,measured=hat,pulseX=x,pulsePhase=0;
  let mode=p.scenario==='balance'?'balance':p.scenario==='swing'?'swing':p.scenario;
  const recovery=new RailRecovery(),spin=new SpinRecovery();
  const uprightOnly=p.scenario==='balance',uprightReturn=new SpinRecovery();
  let quiet=0,elapsed=0,watchElapsed=0,watch=true,watchAngle=q,excursion=0,travel=0,stable=0,longest=0,firstCatch=null;
  let vTarget=0,xTarget=x,held=0,ri=0,previousA=p.initialA,delayed=[];
  const period=Math.max(1,Math.round(p.commandMs)),sensorPeriod=Math.max(1,Math.round(p.encoderMs)),delay=Math.round(p.delayMs);
  const summary={status:'complete',fault:null,peakX:Math.abs(x),peakPulseX:Math.abs(x),peakV:0,peakA:0,peakJ:0,
    peakActualA:0,peakHz:0,saturatedSeconds:0,brakingSeconds:0,recoverySeconds:0,recoveries:0,spinRecoveries:0,spinRecoverySeconds:0,catches:0,finalStable:0,longestStable:0,firstCatch:null};
  function save(t,request,a,jerk){trace.push({t,theta:q,omega:w,thetaHat:hat,x,pulseX,v:s.v,actualV,a:s.a,actualA:a,
    request,jerk,hz:Math.abs(s.v)*p.stepsPerM,mode,braking:!!s.brake});}
  function returnUpright(t,reason){uprightReturn.begin(Math.round(t*1e6));mode='bal_brake';watch=false;events.push({t,event:reason});}
  save(0,0,0,0);
  for(let i=0;i<Math.round(p.duration/dt);i++){
    const t=i*dt;
    if(i%sensorPeriod===0)measured=wrap(Math.round((q+p.encoderOffsetDeg*PI/180)*4096/(2*PI))*2*PI/4096);
    delayed.push(measured); const sensed=delayed.length>delay?delayed.shift():delayed[0];
    const ew=2*PI*p.bw,error=wrap(sensed-hat);
    hat=wrap(hat+(rate+2*ew*error)*dt);rate+=ew*ew*error*dt;
    const balance=-(k[0]*hat+k[1]*rate+k[2]*pulseX+k[3]*s.v);
    const spinNow=i*1000;
    if(uprightOnly && mode==='balance' && Math.abs(wrap(sensed))>50*PI/180)returnUpright(t,'upright fall >50deg');
    if(!uprightOnly && ['swing','balance','rail_brake','rail_return'].includes(mode) && spinTrigger(rate)){
      spin.begin(spinNow);recovery.reset();watch=false;quiet=0;elapsed=0;
      mode='spin_brake';summary.spinRecoveries++;events.push({t,event:'pendulum overspeed recovery'});
    }
    if((mode==='swing'||mode==='balance') && recovery.atEdge(pulseX,p.rail)){
      if(uprightOnly)returnUpright(t,'upright rail protection');
      else {recovery.begin(pulseX,p.rail,s.brake);mode='rail_brake';summary.recoveries++;events.push({t,event:'rail recovery'});}
    }
    let request=0;
    if(mode==='swing'){
      elapsed+=dt;
      const en=.5*p.controllerLength/G*rate*rate+Math.cos(hat);
      request=p.ke*(en-1)*Math.tanh(rate*Math.cos(hat)/p.phase_soft)-p.kpx*pulseX-p.kdx*s.v;
      quiet=Math.abs(rate)<.15 && Math.abs(wrap(hat-PI))<.08?quiet+dt:0;
      if(quiet>.30 && elapsed<1.5 && Math.abs(pulseX)<.1)request=Math.min(1,p.amax_s);
      request=clamp(request,-p.amax_s,p.amax_s);
      if(canCapture(p,hat,rate,pulseX,s.v,s.a)){
        mode='balance';request=clamp(balance,-p.amax_b,p.amax_b);watch=false;summary.catches++;if(firstCatch===null)firstCatch=t;events.push({t,event:'caught'});
      }
    }else if(mode==='balance'){
      request=clamp(balance,-p.amax_b,p.amax_b);
      if(!uprightOnly && Math.abs(hat)>p.giveup){mode='swing';events.push({t,event:'lost balance'});}
    }else if(mode==='bal_brake'||mode==='bal_center'){
      uprightReturn.update(pulseX,s,0,false,spinNow);
      if(uprightReturn.phase===3){mode='idle';s={v:0,a:0,brake:0};events.push({t,event:'upright centered; stopped'});}
      else if(uprightReturn.timedOut(spinNow)){summary.fault='Upright centering timeout';events.push({t,event:summary.fault});break;}
      else{mode=uprightReturn.phase===1?'bal_brake':'bal_center';request=uprightReturn.demand(pulseX,s,p.vmax,Math.max(p.amax_s,p.amax_b),p.jmax,dt);}
    }else if(mode==='rail_brake'||mode==='rail_return'){
      if(recovery.update(pulseX,s,dt)){
        mode='swing';quiet=0;elapsed=dt;
        const en=.5*p.controllerLength/G*rate*rate+Math.cos(hat);
        request=clamp(p.ke*(en-1)*Math.tanh(rate*Math.cos(hat)/p.phase_soft)-p.kpx*pulseX-p.kdx*s.v,-p.amax_s,p.amax_s);
        events.push({t,event:'return inside complete',x:pulseX,v:s.v,a:s.a});
      }else if(recovery.elapsed>8){summary.fault='Rail recovery timeout';events.push({t,event:summary.fault});break;}
      else {mode=recovery.phase===2?'rail_return':'rail_brake';request=recovery.demand(pulseX,s,p.vmax,Math.max(p.amax_s,p.amax_b),p.jmax,dt);}
    }else if(['spin_brake','spin_center','spin_wait'].includes(mode)){
      if(spin.update(pulseX,s,rate,true,spinNow)){
        mode='swing';quiet=0;elapsed=dt;
        watch=true;watchAngle=sensed;excursion=0;travel=0;watchElapsed=0;
        const en=.5*p.controllerLength/G*rate*rate+Math.cos(hat);
        request=clamp(p.ke*(en-1)*Math.tanh(rate*Math.cos(hat)/p.phase_soft)-p.kpx*pulseX-p.kdx*s.v,-p.amax_s,p.amax_s);
        events.push({t,event:'spin recovery complete',omega:rate,x:pulseX,velocity:s.v,acceleration:s.a});
      }else if(spin.timedOut(spinNow)){summary.fault='Spin recovery centering timeout';events.push({t,event:summary.fault});break;}
      else{mode=spin.phase===1?'spin_brake':spin.phase===2?'spin_center':'spin_wait';request=spin.demand(pulseX,s,p.vmax,Math.max(p.amax_s,p.amax_b),p.jmax,dt);}
    }else if(mode==='sine'||mode==='reversal'){
      const target=p.manualSpeed*(mode==='sine'?Math.sin(2*PI*p.frequency*t):(Math.floor(t*p.frequency*2)%2?-1:1));
      request=velocityAccel(s.v,target,p.amax_s,p.jmax,dt);
    }else if(replay){
      while(ri<recorded.points.length-1 && recorded.points[ri+1][0]<=t)ri++;
      request=recorded.points[ri][4];
      if(t>recorded.points.at(-1)[0])break;
    }
    const drive=['bal_brake','bal_center','rail_brake','rail_return','spin_brake','spin_center','spin_wait'].includes(mode)?Math.max(p.amax_s,p.amax_b):mode==='balance'?p.amax_b:p.amax_s;
    // Experimental command adapters. No claim of matching a named driver library.
    if(p.style==='velocity'||p.style==='position'){
      if(i%period===0){
        vTarget=clamp(s.v+request*period*dt,-p.vmax,p.vmax);
        xTarget+=vTarget*period*dt;held=vTarget;
      }
      const target=p.style==='velocity'?held:clamp(p.positionGain*(xTarget-pulseX),-p.vmax,p.vmax);
      request=velocityAccel(s.v,target,drive,p.jmax,dt);
      // Avoid accumulating inaccessible position targets while braking at a rail.
      if(s.brake)xTarget=pulseX;
    }
    s=(mode==='decay'||mode==='idle')?{v:0,a:0,brake:0}:advance(s,pulseX,request,p,drive,dt);
    if(s.brake && (mode==='swing'||mode==='balance')){
      if(uprightOnly)returnUpright(t,'upright predictive rail protection');
      else {recovery.begin(pulseX,p.rail,s.brake);mode='rail_brake';summary.recoveries++;events.push({t,event:'predictive rail recovery'});}
    }
    const jerk=(s.a-previousA)/dt;previousA=s.a;
    const hz=Math.abs(s.v)*p.stepsPerM;
    let fault=hz>p.pulseMax?'STEP pulse-rate ceiling':Math.abs(s.v)>p.vmax+.002?'Command speed limit':null;
    if(fault){summary.fault=fault;events.push({t,event:fault});break;}
    // Mean DDS pulse count over each control interval. The mechanical plant uses
    // the smooth trajectory; this does not model individual step impulses/resonance.
    pulsePhase+=Math.floor(hz*4294967296/(1000000/7))*(1000000/7)*dt/4294967296;
    const steps=Math.floor(pulsePhase);pulsePhase-=steps;pulseX+=Math.sign(s.v)*steps/p.stepsPerM;
    const oldV=actualV;
    actualV=p.lagMs>0?actualV+(p.tracking*s.v-actualV)*(1-Math.exp(-dt/(p.lagMs*.001))):p.tracking*s.v;
    const a=(actualV-oldV)/dt;x+=(oldV+actualV)*.5*dt;
    [q,w]=integrate(q,w,a,p,dt);
    if(watch && ['swing','rail_brake','rail_return'].includes(mode))watchElapsed+=dt;
    excursion=Math.max(excursion,Math.abs(wrap(measured-watchAngle)));travel+=Math.abs(s.v)*dt;
    if(excursion>.03)watch=false;
    if(Math.abs(x)>=p.rail)fault='Physical rail reached';
    else if(Math.abs(pulseX)>p.rail-.01)fault='Pulse-position rail fault';
    else if(['swing','rail_brake','rail_return'].includes(mode) && watch && watchElapsed>2 && travel>.03)fault='No pendulum response';
    if(![q,w,x,s.v,s.a].every(Number.isFinite))fault='Numerical failure';
    if(Math.abs(request-s.a)>.01)summary.saturatedSeconds+=dt;
    if(s.brake)summary.brakingSeconds+=dt;
    if(mode==='rail_brake'||mode==='rail_return')summary.recoverySeconds+=dt;
    if(['spin_brake','spin_center','spin_wait'].includes(mode))summary.spinRecoverySeconds+=dt;
    summary.peakX=Math.max(summary.peakX,Math.abs(x));summary.peakPulseX=Math.max(summary.peakPulseX,Math.abs(pulseX));
    summary.peakV=Math.max(summary.peakV,Math.abs(s.v));summary.peakA=Math.max(summary.peakA,Math.abs(s.a));
    summary.peakJ=Math.max(summary.peakJ,Math.abs(jerk));summary.peakActualA=Math.max(summary.peakActualA,Math.abs(a));summary.peakHz=Math.max(summary.peakHz,hz);
    stable=mode==='balance'&&Math.abs(q)<.1&&Math.abs(x)<.1?stable+dt:0;longest=Math.max(longest,stable);
    if(i%10===9||fault)save((i+1)*dt,request,a,jerk);
    if(fault){summary.fault=fault;events.push({t:(i+1)*dt,event:fault});break;}
  }
  Object.assign(summary,{status:summary.fault?'fault':stable>=5?'balanced':p.scenario==='swing'||p.scenario==='balance'?'not settled':'complete',
    finalStable:stable,longestStable:longest,firstCatch,duration:trace.at(-1).t});
  return {parameters:p,trace,summary,events};
}
function decay(capture,input={}){
  const p=parameters(input),result=[];
  let q=PI+capture.window[0][1],w=0,t=0,ss=0;
  const origin=capture.window[0][0];
  for(const [at,observed] of capture.window){
    while(t<at-origin-1e-9){const h=Math.min(.001,at-origin-t);[q,w]=integrate(q,w,0,p,h);t+=h;}
    const predicted=wrap(q-PI),error=wrap(predicted-observed);ss+=error*error;
    result.push({t:at,observed,predicted});
  }
  return {points:result,rmseDeg:Math.sqrt(ss/result.length)*180/PI};
}
function consoleCommands(input){
  const p=parameters(input);
  const names=['vmax','amax_s','amax_b','jmax','ke','kpx','kdx','phase_soft','rail','pw','bal_pw','pz','pc1','pc2','catch_a','catch_r','giveup','bw'];
  return ['stop',...names.map(k=>`set ${k} ${Number(p[k].toFixed(6))}`),`set leff ${Number(p.controllerLength.toFixed(6))}`,'params'].join('\n');
}
const api={consoleCommands,defaults,styles,parameters,gains,velocityAccel,settledVelocityAccel,stoppingDistance,advance,RailRecovery,SpinRecovery,spinTrigger,spinConfig,canCapture,integrate,simulate,decay,wrap};
if(typeof module!=='undefined')module.exports=api;else root.PendulumSim=api;
})(typeof window==='undefined'?globalThis:window);
