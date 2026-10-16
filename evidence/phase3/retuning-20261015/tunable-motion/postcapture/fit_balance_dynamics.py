import json,sys
from pathlib import Path
import numpy as np
def savgol_filter(values, window, order, deriv=0, delta=1):
    from math import factorial
    x=np.arange(-(window//2),window//2+1)*delta
    weights=np.linalg.pinv(np.column_stack([x**i for i in range(order+1)]))[deriv]*factorial(deriv)
    return np.convolve(np.pad(values,window//2,mode="edge"),weights[::-1],mode="valid")
segments=[]
for d in Path(sys.argv[1]).iterdir():
 if not (d/'report.json').exists():continue
 r=json.loads((d/'report.json').read_text()); rows=[q['state'] for q in map(json.loads,next(d.glob('rig-*.jsonl')).read_text().splitlines()) if q['type']=='state']
 t=np.array([q['unwrapped_us'] for q in rows])*1e-6; mode=np.array([q['mode'] for q in rows]); ix=np.flatnonzero(mode==3)
 if len(ix)==0:continue
 groups=np.split(ix,np.flatnonzero((np.diff(ix)!=1)|(np.diff(t[ix])>.03))+1)
 for g in groups:
  if t[g[-1]]-t[g[0]]<2:continue
  tt=np.arange(t[g[0]],t[g[-1]],.004);theta=np.interp(tt,t[g],[rows[k]['theta'] for k in g]);a=np.interp(tt,t[g],[rows[k]['acceleration'] for k in g]); v=np.interp(tt,t[g],[rows[k]['velocity'] for k in g]);
  smooth=savgol_filter(theta,21,3); w=savgol_filter(theta,21,3,deriv=1,delta=.004);alpha=savgol_filter(theta,21,3,deriv=2,delta=.004)
  segments.append((d.name,tt,smooth,w,alpha,a,v))
results=[]
for delay in np.arange(-.02,.101,.004):
 X=[];Y=[]
 for name,t,q,w,alpha,a,v in segments:
  aa=np.interp(t-delay,t,a);mask=(t>t[0]+.2)&(t<t[-1]-.15)&(abs(q)<.35)&(abs(v)<1.4)
  xx=np.column_stack([np.sin(q),-aa*np.cos(q),-w,-np.tanh(w/.2),np.cos(q)])
  X.extend(xx[mask]);Y.extend(alpha[mask])
 X=np.array(X);Y=np.array(Y);beta=np.linalg.lstsq(X,Y,rcond=None)[0];res=Y-X@beta
 results.append({'delay_ms':round(delay*1000),'coefficients':beta.tolist(),'rmse':float(np.sqrt(np.mean(res**2))),'condition_scaled':float(np.linalg.cond(X/np.sqrt(np.mean(X**2,axis=0)))),'n':len(Y)})
print(json.dumps({'note':'Exploratory closed-loop fit to encoder angle and commanded acceleration; not independent motor measurement or approved calibration','segments':[s[0] for s in segments],'best':sorted(results,key=lambda r:r['rmse'])[:5],'zero_delay':min(results,key=lambda r:abs(r['delay_ms']))},indent=2))
