import numpy as np,json
from pathlib import Path
from scipy.integrate import solve_ivp
from scipy.optimize import least_squares
for name in ['recenter_09','recenter_11']:
 d=Path('experiments/20261012_balance_tuning')/name
 if not d.exists():continue
 r=np.genfromtxt(next(d.glob('*.csv')),names=True,delimiter=',')
 t=r['t_ms']/1000
 # Keep only the final contiguous stationary IDLE interval; no bridged gaps.
 good=(r['mode']==0)&(abs(r['v'])<1e-4)
 i=len(r)-1
 while i>0 and good[i-1] and 0<t[i]-t[i-1]<.15:i-=1
 z=r[i:];t=t[i:]-t[i];q=np.unwrap(z['theta']);q-=q[-1]
 if len(q)<50 or t[-1]<2:continue
 t=t[::2];q=q[::2]
 def pred(p):
  L,b,c,offset,q0,w0=p
  sol=solve_ivp(lambda _,y:[y[1],-9.81/L*np.sin(y[0])-b*y[1]-c*np.tanh(y[1]/.05)],(0,t[-1]),[q0,w0],t_eval=t,rtol=1e-5,atol=1e-7,max_step=.02)
  return sol.y[0]+offset
 z0=[.164,.2,.1,0,q[0],0]
 fit=least_squares(lambda p:pred(p)-q,z0,bounds=([.07,0,0,-.2,q[0]-.2,-5],[.3,4,4,.2,q[0]+.2,5]),loss='soft_l1',f_scale=.015,max_nfev=120)
 out={'source':name,'duration':float(t[-1]),'n':len(t),'parameters':dict(zip(['leff','damping','friction','offset','q0','w0'],fit.x.tolist())),'period_s':float(2*np.pi*np.sqrt(fit.x[0]/9.81)),'rmse_deg':float(np.degrees(np.sqrt(np.mean((pred(fit.x)-q)**2)))),'amplitude_deg':float(np.degrees(np.ptp(q)/2))}
 print(json.dumps(out),flush=True)
 (d/'decay_fit.json').write_text(json.dumps(out,indent=2)+'\n')
