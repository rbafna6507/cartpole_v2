'use strict';
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const original=fs.readFileSync(path.join(__dirname,'baseline_engine.js'),'utf8');
const candidate=`
function forecastCapture(p,theta,omega,x,v,a){
 const k=gains(p),dt=.005;
 let s={v,a,brake:0};
 // Predict the actual governed balance request, including velocity/rail limits.
 // No damping assumed; this is a feasibility screen, not identified hardware.
 for(let i=0;i<60;i++){
  const demand=-(k[0]*theta+k[1]*omega+k[2]*x+k[3]*s.v);
  s=advance(s,x,demand,p,p.amax_b,dt);
  if(s.brake||Math.abs(s.v)>.95*p.vmax)return false;
  x+=s.v*dt;
  const alpha=(G*Math.sin(theta)-s.a*Math.cos(theta))/p.controllerLength;
  theta+=omega*dt+.5*alpha*dt*dt;omega+=alpha*dt;
  if(Math.abs(theta)>=p.giveup || Math.abs(x)>=p.rail-.025)return false;
 }
 return true;
}
function shapeApproach(p,theta,omega,x,v,a,request){
 if(Math.abs(theta)>=.8 || Math.abs(omega)>=p.catch_r || (theta*omega>0 && Math.abs(theta)>.2))return request;
 const u=clamp((.8-Math.abs(theta))/.5,0,1),weight=u*u*(3-2*u);
 const k=gains(p),demand=clamp(-(k[0]*theta+k[1]*omega+k[2]*x+k[3]*v),-p.amax_b,p.amax_b);
 return request+weight*(demand-request);
}
`;
function engine(kind){
 let code=original;
 if(kind!=='baseline'){
  code=code.replace('function canCapture(',candidate+'\nfunction canCapture(');
  code=code.replace('return Math.abs(theta+omega*ramp+.5*alpha*ramp*ramp)<p.giveup;',`return forecastCapture(p,theta,omega,x,v,acceleration);`);
 }
 if(kind.includes('shape')){
  code=code.replace('if(canCapture(p,hat,rate,pulseX,s.v,s.a)){',`request=shapeApproach(p,hat,rate,pulseX,s.v,s.a,request);
      if(Math.abs(balance-request)<=.02*p.jmax && canCapture(p,hat,rate,pulseX,s.v,s.a)){`);
 }
 if(kind.includes('return'))code=code.replace('if(this.phase===2 && inward && Math.abs(x)<=this.exitBoundary)', 'if(this.phase===2 && inward && Math.abs(x)<=this.exitBoundary && Math.abs(s.a)<=1.5 && Math.abs(s.v)<=.20)');
 const ctx={module:{exports:{}}};vm.runInNewContext(code,ctx);return ctx.module.exports;
}
const variants=['baseline','forecast','shape','forecast_return','shape_return'];
const settings=[{name:'12/12/60',amax_s:12,amax_b:12,jmax:60},{name:'16/16/70',amax_s:16,amax_b:16,jmax:70},{name:'20/16/40',amax_s:20,amax_b:16,jmax:40}];
const rows=[];
for(const variant of variants){
 const E=engine(variant);
 for(const limits of settings)for(const initialAngle of [-2,0,2]){
  const r=E.simulate({...limits,initialAngle,duration:30});
  const captures=r.events.filter(e=>e.event==='caught');
  let shortCaptures=0;
  for(const c of captures){const end=r.events.find(e=>e.t>=c.t && e!==c && ['lost balance','predictive rail recovery','rail recovery'].includes(e.event));if(end&&end.t-c.t<.3)shortCaptures++;}
  const row={variant,limits:limits.name,initialAngle,...r.summary,shortCaptures};rows.push(row);
 }
 console.log(variant,JSON.stringify(rows.filter(r=>r.variant===variant).map(r=>({limits:r.limits,angle:r.initialAngle,status:r.status,catches:r.catches,short:r.shortCaptures,rail:r.recoveries,stable:+r.longestStable.toFixed(2),peakA:+r.peakA.toFixed(2)}))));
}
fs.writeFileSync(path.join(__dirname,'screen.json'),JSON.stringify(rows,null,2)+'\n');
