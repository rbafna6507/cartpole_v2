from pathlib import Path
import json, math, hashlib
import numpy as np
P=Path('/tmp/cartpole-retune-20261015/natural351-first-trials');R=180/np.pi
wrap=lambda a: (np.asarray(a)+np.pi)%(2*np.pi)-np.pi
passive=next(P.glob('assisted-*'))
ps=[json.loads(l) for l in (passive/'states.jsonl').read_text().splitlines()];pc=[json.loads(l) for l in (passive/'camera.jsonl').read_text().splitlines()]
end=ps[-1]['state']['received_ns']/1e9
anchor=float(np.median([v['snapshot']['theta_rad'] for v in pc if end-10<=v['snapshot'].get('t',0)<=end and v['snapshot'].get('angle_valid')]))
runs=[]
for d in sorted(P.glob('natural351-auto*a-*')):
 rep=json.loads((d/'report.json').read_text());cam=json.loads((d/'camera.json').read_text());events=[json.loads(l) for l in next(d.glob('rig-*.jsonl')).read_text().splitlines()];states=[e['state'] for e in events if e['type']=='state']
 # A fixed empirical lower-envelope board-to-host receipt mapping, solely for offline lag scanning.
 board=np.array([s['unwrapped_us']/1e6 for s in states]); recv=np.array([s['received_ns']/1e9 for s in states]); origin=float(np.quantile(recv-board,.01));time=board+origin
 theta=np.unwrap([s['theta'] for s in states]);omega=np.array([s['omega'] for s in states]);mode=np.array([s['mode'] for s in states])
 start=rep['motion_start']['received_ns']/1e9
 valid=[]
 for c in cam:
  if not(start<=c['t']<=start+8) or not c['detected'] or c['pivot_px'] is None or c['bob_px'] is None: continue
  dx,dy=np.array(c['bob_px'])-c['pivot_px']; raw=math.atan2(dx,dy); target=float(wrap(np.pi-raw-0.006486665936711519-anchor))
  valid.append(dict(c,target=target,length=math.hypot(dx,dy)))
 runs.append(dict(name=d.name.split('-')[1],path=str(d),report=rep,time=time,theta=theta,omega=omega,mode=mode,valid=valid,cam=cam,states=states,start=start,origin=origin,latency=(recv-board-origin)*1000))

def samples(run,lag):
 c=run['valid'];t=np.array([x['t'] for x in c])-lag
 ix=np.searchsorted(run['time'],t);good=(ix>0)&(ix<len(run['time']));i=np.clip(ix,1,len(run['time'])-1);gap=run['time'][i]-run['time'][i-1];good&=gap<=.030
 # Source-health/provenance gate, and explicit observable geometric filter.
 health=np.array([s['fault']==0 and (s['flags']&1)!=0 for s in run['states']]);good &=health[i]&health[i-1]
 good &= np.array([x['confidence']>=.8 and 115<=x['length']<=155 for x in c])
 e=wrap(np.interp(t,run['time'],run['theta']));om=np.interp(t,run['time'],run['omega']);v=np.array([x['target'] for x in c]);m=run['mode'][i-1]
 return np.c_[e,wrap(v-e),om,t-run['start'],m,np.array([x['length'] for x in c]),np.array([x['confidence'] for x in c])][good]

def basis(x,kind):
 e=x[:,0];w=x[:,2]
 if kind=='raw': return np.zeros((len(e),0))
 if kind=='offset':return np.ones((len(e),1))
 k=int(kind[1]); cols=[] if kind.startswith('a') else [np.ones(len(e))]
 for j in range(1,k+1):cols += [np.sin(j*e),1-np.cos(j*e)]
 if kind.endswith('h'):cols += [np.sign(w)]
 return np.array(cols).T

def fit(x,k):
 A=basis(x,k); y=x[:,1];b=np.zeros(A.shape[1])
 for _ in range(12):
  err=wrap(y-A@b); wt=np.minimum(1,math.radians(5)/np.maximum(np.abs(err),1e-12));b=np.linalg.lstsq(A*np.sqrt(wt)[:,None],y*np.sqrt(wt),rcond=None)[0]
 return b

def metrics(x,k,b):
 e=wrap(x[:,1]-basis(x,k)@b)*R
 return dict(n=len(e),rmse_deg=float(np.sqrt(np.mean(e**2))),median_abs_deg=float(np.median(abs(e))),p95_abs_deg=float(np.quantile(abs(e),.95)),bias_deg=float(np.median(e)),max_abs_deg=float(max(abs(e))))

def objective(x,k,b):
 e=abs(wrap(x[:,1]-basis(x,k)@b));delta=math.radians(5);return float(np.mean(np.where(e<=delta,e*e/2,delta*(e-delta/2))))

result={'anchor_theta_rad':anchor,'anchor_theta_deg':anchor*R,'time_convention':'encoder board time plus per-run 1st percentile serial receipt minus board time. Compare camera host-read t minus effective lag; lag absorbs unknown capture and serial delays, not an exposure calibration.','source_quality':[],'models':{}}
for r in runs:
 c=r['cam'];active=[x for x in c if r['start']<=x['t']<=r['start']+8];x=samples(r,0)
 q=dict(run=r['name'],active_camera_n=len(active),detected_n=sum(x['detected'] for x in active),admitted_n=len(x),angle_bins_counts=np.histogram(x[:,0]*R,bins=np.arange(-180,181,30))[0].tolist(),serial_receipt_residual_ms_pcts=np.percentile(r['latency'],[0,50,95,99,100]).tolist(),camera_t_gap_ms_pcts=np.percentile(np.diff([x['t'] for x in active])*1000,[0,50,95,100]).tolist(),camera_read_to_observer_ms_pcts=np.percentile([(x['receipt_s']-x['t'])*1000 for x in active],[0,50,95,100]).tolist())
 result['source_quality'].append(q)
print('ANCHOR',anchor,anchor*R)
print('QUALITY',json.dumps(result['source_quality']))
for kind in ['raw','offset','a1','a2','f2','a2h']:
 scans=[]
 for lag in np.arange(-.080,.1201,.001):
  xs=[samples(r,lag) for r in runs];x=np.vstack(xs);b=fit(x,kind);scans.append((objective(x,kind,b),float(lag),b,x,xs))
 _,lag,b,x,xs=min(scans,key=lambda v:v[0]);out=dict(lag_ms=lag*1000,coef_rad=b.tolist(),pooled=metrics(x,kind,b),per_run=[metrics(z,kind,b) for z in xs],scan=[{'lag_ms':ll*1000,'loss':loss} for loss,ll,*_ in scans[::5]])
 cv=[]
 for j in range(2):
  tr=[]
  for lag1 in np.arange(-.080,.1201,.001):
   z=samples(runs[j],lag1);bb=fit(z,kind);tr.append((objective(z,kind,bb),float(lag1),bb,z))
  _,ll,bb,z=min(tr,key=lambda v:v[0]);zz=samples(runs[1-j],ll);cv.append(dict(train=runs[j]['name'],test=runs[1-j]['name'],lag_ms=ll*1000,coef_rad=bb.tolist(),train_metrics=metrics(z,kind,bb),test_metrics=metrics(zz,kind,bb)))
 out['leave_one_training_run_out']=cv
 result['models'][kind]=out
 print(kind,'lag',round(lag*1000,2),'coefdeg',b*R,'pooled',out['pooled'],'cross',[(c['lag_ms'],c['test_metrics']) for c in cv])
 # Return direction residual distributions within 30deg angle bins and low/high rates.
 if kind=='a2':
  result['a2_angle_direction_bins']=[]
  for lo in range(-180,180,30):
   sel=(x[:,0]*R>=lo)&(x[:,0]*R<lo+30); row={'lo_deg':lo,'n':int(sum(sel))}
   for nam,mask in [('positive',x[:,2]>1),('negative',x[:,2]<-1),('slow',abs(x[:,2])<=1)]:
    zz=x[sel&mask];row[nam]={'n':len(zz),'median_residual_deg':float(np.median(wrap(zz[:,1]-basis(zz,kind)@b)*R)) if len(zz) else None}
   result['a2_angle_direction_bins'].append(row)
  result['a2_lag_sensitivity']=[dict(lag_ms=lag1*1000,metrics=metrics(np.vstack([samples(r,lag1) for r in runs]),kind,b)) for lag1 in [lag-.010,lag,lag+.010]]
 # At nominal22ms and no effective offset, with same model form refitted.
 out['fixed_22ms']=metrics(np.vstack([samples(r,.022) for r in runs]),kind,fit(np.vstack([samples(r,.022) for r in runs]),kind))
result['sha256']={str(f.relative_to(P)):hashlib.sha256(f.read_bytes()).hexdigest() for r in runs for f in Path(r['path']).iterdir() if f.suffix in ['.json','.jsonl']}
result['sha256'].update({str(f.relative_to(P)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [passive/'camera.jsonl',passive/'states.jsonl',passive/'operator-notes.json']})
Path('/tmp/cartpole-retune-20261015/natural351-map-exploration.json').write_text(json.dumps(result,indent=2)+'\n')
