from pathlib import Path
import numpy as np,json
from scipy.signal import find_peaks
from scipy.integrate import solve_ivp
from scipy.optimize import least_squares
OUT=Path(__file__).resolve().parent/'sep18';r=np.genfromtxt(OUT/'run_20260918_103825.csv',names=True,delimiter=',');t=(r['t_ms']-r['t_ms'][0])/1000
q=np.unwrap(r['theta']);windows=[(105,111),(111,114),(294,301),(301,305)]
results=[]
for lo,hi in windows:
 ix=(t>=lo)&(t<=hi);ts=t[ix]-t[ix][0];obs=q[ix];center=np.median(q[(t>hi)&(t<hi+3)]);obs=obs-center
 peaks,_=find_peaks(obs,prominence=.03,distance=10)
 print('window',lo,hi,'peaks',list(zip(ts[peaks].round(3),np.degrees(obs[peaks]).round(1))),'periods',np.diff(ts[peaks]))
 def pred(z):
  L,b,c,offset,q0,w0=z
  sol=solve_ivp(lambda _,y:[y[1],-9.81/L*np.sin(y[0])-b*y[1]-c*np.tanh(y[1]/.05)],(0,ts[-1]),[q0,w0],t_eval=ts,rtol=2e-6,atol=1e-8,max_step=.025)
  return sol.y[0]+offset
 z0=[.12445,.913,0,0,obs[0],r['theta_dot'][ix][0]]
 fit=least_squares(lambda z:pred(z)-obs,z0,bounds=([.07,0,0,-.3,obs[0]-.5,-35],[.2,4,10,.3,obs[0]+.5,35]),max_nfev=150,loss='soft_l1',f_scale=.03)
 zz=fit.x.tolist();prior=pred(z0)
 print('FIT',zz,'rmse_deg',np.degrees(np.sqrt(np.mean((pred(fit.x)-obs)**2))),'prior',np.degrees(np.sqrt(np.mean((prior-obs)**2))))
 results.append({'window':[lo,hi],'parameters':dict(zip(['leff','damping','coulomb','offset','q0','w0'],zz)),'rmse_deg':float(np.degrees(np.sqrt(np.mean((pred(fit.x)-obs)**2)))),'points':np.column_stack([ts,obs,pred(fit.x),prior]).tolist()})
(OUT/'decay_fit.json').write_text(json.dumps(results,indent=2))
