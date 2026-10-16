import gzip,json,sys,math
import numpy as np
from pathlib import Path
root=Path('/tmp/cartpole-slow-swing')
rig=[json.loads(l) for l in open('/home/rbafna/cartpole-v2-live/releases/platform-20261014-cart-switches/runs/rig/rig-1791998096956761701-3206829725.jsonl')]
vis=[json.loads(l) for l in open('/home/rbafna/cartpole-v2-runs/vision-encoder-check-30fps/20261014_131151_535631/states.jsonl')]
states=[r['state'] for r in rig if r.get('type')=='state'];t=np.array([s['received_ns']/1e9 for s in states]);x=np.array([s['x'] for s in states]);mode=np.array([s['mode'] for s in states])
valid=[v for v in vis if v.get('pivot_px') and v.get('detected') and v.get('confidence',0)>.7]
vt=np.array([v['t'] for v in valid]);vx=np.array([v['pivot_px'][0] for v in valid]);vy=np.array([v['pivot_px'][1] for v in valid]);sx=np.interp(vt,t,x);sm=np.array([states[min(len(states)-1,np.searchsorted(t,z))]['mode'] for z in vt])
# Use first measured leftwards home section only. Exclude start/stop and camera outliers.
sel=(sm==13)&(vt<93418)&(vt>93409)&(vy>30)&(vy<280)
coef=np.polyfit(sx[sel],vx[sel],1);pred=np.polyval(coef,sx);err=(vx-pred)/coef[0]
print('home_fit',coef.tolist(),'n',sum(sel),'residual_mm',np.quantile(np.abs(err[sel]),[.5,.95,1]).tolist())
commands=[r for r in rig if r.get('type')=='command' and r['payload'].split()[1] not in ('PING','STATUS')]
for r in commands:print(r['host_monotonic_ns']/1e9,r['payload'])
segments=[];start=None
for i,s in enumerate(states):
 if s['flags']&2 and start is None:start=i
 if (not s['flags']&2 or i==len(states)-1) and start is not None:
  a,b=t[start],t[i];idx=(vt>=a)&(vt<=b)&(vy>30)&(vy<280)
  print('segment',a,b,'mode',states[start]['mode'],'n',sum(idx),'pixelx',np.quantile(vx[idx],[0,.5,1]).tolist() if any(idx) else None,'motion_error_mm',np.quantile(err[idx]*1000,[0,.1,.5,.9,1]).tolist() if any(idx) else None)
  segments.append((a,b,idx));start=None
