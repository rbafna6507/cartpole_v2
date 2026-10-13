from pathlib import Path
import numpy as np,json
from scipy.integrate import solve_ivp
from scipy.optimize import least_squares
O=Path(__file__).resolve().parent/'sep18';r=np.genfromtxt(O/'run_20260918_103825.csv',names=True,delimiter=',');t=(r['t_ms']-r['t_ms'][0])/1000;q=np.unwrap(r['theta']);fit=json.loads((O/'decay_fit.json').read_text())[0]['parameters'];models={'prior':[.1244548878,.9133833709,0],'recent_provisional':[fit[k] for k in ['leff','damping','coulomb']]};rows=[]
for name,(L,b,c) in models.items():
 for lo,hi in [(105,111),(294,301)]:
  ix=(t>=lo)&(t<=hi);ts=t[ix]-t[ix][0];center=np.median(q[(t>hi)&(t<hi+3)]);obs=q[ix]-center
  def pred(z):
   q0,w0,offset=z
   return solve_ivp(lambda _,y:[y[1],-9.81/L*np.sin(y[0])-b*y[1]-c*np.tanh(y[1]/.05)],(0,ts[-1]),[q0,w0],t_eval=ts,max_step=.025,rtol=2e-6,atol=1e-8).y[0]+offset
  z0=[obs[0],r['theta_dot'][ix][0],0]
  f=least_squares(lambda z:pred(z)-obs,z0,bounds=([obs[0]-.5,-35,-.3],[obs[0]+.5,35,.3]),loss='soft_l1',f_scale=.03,max_nfev=100)
  row={'model':name,'window':[lo,hi],'plant':[L,b,c],'initial_nuisance_fit':f.x.tolist(),'rmse_deg':float(np.degrees(np.sqrt(np.mean((pred(f.x)-obs)**2)))),'points':np.column_stack([ts,obs,pred(f.x)]).tolist()};rows.append(row);print(name,lo,row['rmse_deg'])
(O/'decay_validation.json').write_text(json.dumps(rows,indent=2))
