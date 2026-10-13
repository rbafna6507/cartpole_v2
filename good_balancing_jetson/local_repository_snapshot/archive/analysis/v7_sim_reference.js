// Archived pre-v8 engine, with initial velocity/rate/acceleration seeding added for comparison.
/* Offline, deterministic 175 mm pendulum model. See README for model boundaries. */
(function(root){
'use strict';
const PI=Math.PI, G=9.81, clamp=(x,l,h)=>Math.max(l,Math.min(h,x));
const wrap=x=>Math.atan2(Math.sin(x),Math.cos(x));
const slew=(x,y,d)=>x+clamp(y-x,-d,d);
const styles={jerk:'Acceleration → jerk-limited DDS',trapezoid:'Acceleration → trapezoidal ramp',velocity:'Sampled velocity setpoints',position:'Streamed position targets'};
const defaults={duration:20, scenario:'swing',style:'jerk',amax_s:6,amax_b:6,jmax:150,vmax:1.5,
  leff:0.165775567724757,controllerLength:0.166,damping:0.4022789826050984,coulomb:0,
  rail:.15,stepsPerM:26666.6667,pulseMax:62500,commandMs:10,positionGain:30,
  tracking:1,lagMs:0,delayMs:0,bw:10,encoderMs:2,initialAngle:0,initialX:0,initialOmega:0,initialV:0,initialA:0,
  ke:2,kpx:30,kdx:.5,phase_soft:1,catch_a:.45,catch_r:3,giveup:.7,
  pw:7,pz:.85,pc1:-.8,pc2:-1.2,manualSpeed:.15,frequency:.5,integrationDt:.001};
function parameters(input={}){
  const p={...defaults,...input};
  const ranges={duration:[.1,120],amax_s:[.01,100],amax_b:[.01,100],jmax:[.1,100000],vmax:[.001,10],
    leff:[.01,1],controllerLength:[.01,1],damping:[0,10],coulomb:[0,20],rail:[.04,2],stepsPerM:[100,1e7],
    pulseMax:[1,1e6],commandMs:[1,200],positionGain:[1,200],tracking:[0,1],lagMs:[0,200],delayMs:[0,100],
    bw:[.1,100],encoderMs:[1,20],initialAngle:[-180,180],initialX:[-1,1],ke:[0,30],kpx:[0,200],kdx:[0,50],
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
function stoppingDistance(v,a,amax,j){
  v=Math.max(0,v);a=clamp(a,-amax,amax);
  const ramp=(a+amax)/j,stop=(a+Math.sqrt(a*a+2*j*v))/j,t=Math.min(ramp,stop);
  let d=v*t+.5*a*t*t-j*t*t*t/6;
  if(stop>ramp)d+=(v+a*t-.5*j*t*t)**2/(2*amax);
  return Math.max(0,d);
}
// Port of swingup/cart_motion.h; parity is checked against the compiled C++ header.
function advance(s,x,request,p,drive,dt){
  const brake=Math.max(p.amax_s,p.amax_b),j=p.style==='trapezoid'?1e12:p.jmax;
  const positive=Math.max(0,velocityAccel(s.v,p.vmax,brake,j,dt));
  const negative=Math.min(0,velocityAccel(s.v,-p.vmax,brake,j,dt));
  let target=clamp(clamp(request,-drive,drive),negative,positive);
  const na=slew(s.a,target,j*dt),nv=s.v+na*dt;
  let dir=s.brake;
  if(dir && s.v*dir<=0 && s.a*dir<=0)dir=0;
  if(!dir)for(const d of [-1,1]){
    const ov=nv*d,oa=na*d,room=p.rail-.015-d*x;
    if((ov>0||oa>0) && Math.max(0,ov)*dt+stoppingDistance(ov,oa,brake,j)>=room){dir=d;break;}
  }
  if(dir)target=-dir*brake;
  const a=slew(s.a,target,j*dt);
  return {v:s.v+a*dt,a,brake:dir};
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
  const p=parameters(input),dt=.001,k=gains(p),trace=[],events=[];
  if(p.scenario==='replay' && !recorded?.points?.length)throw Error('Recorded waveform is unavailable');
  const replay=p.scenario==='replay';
  let q=wrap((p.scenario==='balance'?0:PI)+p.initialAngle*PI/180),w=p.initialOmega,x=p.initialX,actualV=p.initialV;
  if(replay)q=wrap(recorded.points[0][1]+PI);
  let s={v:p.initialV,a:p.initialA,brake:0},hat=q,rate=p.initialOmega,measured=q,pulseX=x,pulsePhase=0;
  let mode=p.scenario==='balance'?'balance':p.scenario==='swing'?'swing':p.scenario;
  let quiet=0,elapsed=0,watch=true,watchAngle=q,excursion=0,travel=0,stable=0,longest=0,firstCatch=null;
  let vTarget=0,xTarget=x,held=0,ri=0,previousA=p.initialA,delayed=[];
  const period=Math.max(1,Math.round(p.commandMs)),sensorPeriod=Math.max(1,Math.round(p.encoderMs)),delay=Math.round(p.delayMs);
  const summary={status:'complete',fault:null,peakX:Math.abs(x),peakPulseX:Math.abs(x),peakV:0,peakA:0,peakJ:0,
    peakActualA:0,peakHz:0,saturatedSeconds:0,brakingSeconds:0,catches:0,finalStable:0,longestStable:0,firstCatch:null};
  function save(t,request,a,jerk){trace.push({t,theta:q,omega:w,thetaHat:hat,x,pulseX,v:s.v,actualV,a:s.a,actualA:a,
    request,jerk,hz:Math.abs(s.v)*p.stepsPerM,mode,braking:!!s.brake});}
  save(0,0,0,0);
  for(let i=0;i<Math.round(p.duration/dt);i++){
    const t=i*dt;
    if(i%sensorPeriod===0)measured=wrap(Math.round(q*4096/(2*PI))*2*PI/4096);
    delayed.push(measured); const sensed=delayed.length>delay?delayed.shift():delayed[0];
    const ew=2*PI*p.bw,error=wrap(sensed-hat);
    hat=wrap(hat+(rate+2*ew*error)*dt);rate+=ew*ew*error*dt;
    const balance=-(k[0]*hat+k[1]*rate+k[2]*pulseX+k[3]*s.v);
    let request=0;
    if(mode==='swing'){
      elapsed+=dt;
      const en=.5*p.controllerLength/G*rate*rate+Math.cos(hat);
      request=p.ke*(en-1)*Math.tanh(rate*Math.cos(hat)/p.phase_soft)-p.kpx*pulseX-p.kdx*s.v;
      quiet=Math.abs(rate)<.15 && Math.abs(wrap(hat-PI))<.08?quiet+dt:0;
      if(quiet>.30 && elapsed<1.5 && Math.abs(pulseX)<.1)request=Math.min(1,p.amax_s);
      request=clamp(request,-p.amax_s,p.amax_s);
      if(Math.abs(hat)<p.catch_a && Math.abs(rate)<p.catch_r && Math.abs(pulseX)<Math.min(.12,p.rail-.03) && Math.abs(s.v)<.8 && Math.abs(balance)<p.amax_b){
        mode='balance';watch=false;summary.catches++;if(firstCatch===null)firstCatch=t;events.push({t,event:'caught'});
      }
    }else if(mode==='balance'){
      request=clamp(balance,-p.amax_b,p.amax_b);
      if(Math.abs(hat)>p.giveup){mode='swing';events.push({t,event:'lost balance'});}
    }else if(mode==='sine'||mode==='reversal'){
      const target=p.manualSpeed*(mode==='sine'?Math.sin(2*PI*p.frequency*t):(Math.floor(t*p.frequency*2)%2?-1:1));
      request=velocityAccel(s.v,target,p.amax_s,p.jmax,dt);
    }else if(replay){
      while(ri<recorded.points.length-1 && recorded.points[ri+1][0]<=t)ri++;
      request=recorded.points[ri][4];
      if(t>recorded.points.at(-1)[0])break;
    }
    const drive=mode==='balance'?p.amax_b:p.amax_s;
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
    s=mode==='decay'?{v:0,a:0,brake:0}:advance(s,pulseX,request,p,drive,dt);
    const jerk=(s.a-previousA)/dt;previousA=s.a;
    const hz=Math.abs(s.v)*p.stepsPerM;
    let fault=hz>p.pulseMax?'STEP pulse-rate ceiling':Math.abs(s.v)>p.vmax+.002?'Command speed limit':null;
    if(fault){summary.fault=fault;events.push({t,event:fault});break;}
    // Mean DDS pulse count over each control interval. The mechanical plant uses
    // the smooth trajectory; this does not model individual step impulses/resonance.
    pulsePhase+=Math.floor(hz*4294967296/125000)*125000*dt/4294967296;
    const steps=Math.floor(pulsePhase);pulsePhase-=steps;pulseX+=Math.sign(s.v)*steps/p.stepsPerM;
    const oldV=actualV;
    actualV=p.lagMs>0?actualV+(p.tracking*s.v-actualV)*(1-Math.exp(-dt/(p.lagMs*.001))):p.tracking*s.v;
    const a=(actualV-oldV)/dt;x+=(oldV+actualV)*.5*dt;
    [q,w]=integrate(q,w,a,p,dt);
    excursion=Math.max(excursion,Math.abs(wrap(measured-watchAngle)));travel+=Math.abs(s.v)*dt;
    if(excursion>.03)watch=false;
    if(Math.abs(x)>=p.rail)fault='Physical rail reached';
    else if(Math.abs(pulseX)>p.rail-.01)fault='Pulse-position rail fault';
    else if(mode==='swing' && watch && t>2 && travel>.03)fault='No pendulum response';
    if(![q,w,x,s.v,s.a].every(Number.isFinite))fault='Numerical failure';
    if(Math.abs(request-s.a)>.01)summary.saturatedSeconds+=dt;
    if(s.brake)summary.brakingSeconds+=dt;
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
const api={defaults,styles,parameters,gains,velocityAccel,stoppingDistance,advance,integrate,simulate,decay,wrap};
if(typeof module!=='undefined')module.exports=api;else root.PendulumSim=api;
})(typeof window==='undefined'?globalThis:window);
