import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import argparse
p=argparse.ArgumentParser(description='Offline normalized-energy diagnostics, not mechanical power metrology.');p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args();base=args.input;args.output.mkdir(parents=True,exist_ok=False)
params=json.loads((base/'report.json').read_text())['test_parameters']
rows=[r['state'] for f in base.glob('rig*.jsonl') for line in f.read_text().splitlines() if (r:=json.loads(line)).get('type')=='state']
rows=sorted({r['unwrapped_us']:r for r in rows}.values(),key=lambda r:r['unwrapped_us'])
t0=next(r['unwrapped_us'] for r in rows if r['mode']==2)
s=[r for r in rows if 0 <= r['unwrapped_us']-t0 < 25e6]
arr=lambda k:np.array([r[k] for r in s]);t=(arr('unwrapped_us')-t0)*1e-6
q=arr('angle_hat');w=arr('omega');x=arr('x');v=arr('velocity');a=arr('acceleration');d=arr('demand');mode=arr('mode')
E=.5*params['leff']/9.81*w*w+np.cos(q);z=w*np.cos(q)
pump=params['ke']*(E-1)*np.tanh(z/params['phase_soft']);center=-params['kpx']*x;damp=-params['kdx']*v
power={name:-u*z/9.81 for name,u in [('pump',pump),('centering',center),('cart_damping',damp),('actual_command',a)]}
m=(t>=10)&(t<=24)&(mode==2)
if m.sum()<100:raise SystemExit('Insufficient late swing-up samples; do not interpret as a limit cycle')
result={'trial':base.name,'parameters':params,'window_s':[10,24], 'caution':'Normalized model-energy work using firmware observer and commanded acceleration, not measured mechanical power. Command terms change under jerk/speed limits; additive request terms do not identify each term causal realized work.'}
result['rms_requests']={k:float(np.sqrt(np.mean(u[m]**2))) for k,u in [('pump',pump),('centering',center),('cart_damping',damp),('sum',pump+center+damp),('demand',d),('commanded_acceleration',a)]}
result['normalized_work_per_s']={k:float(np.trapezoid(u[m],t[m])/(t[m][-1]-t[m][0])) for k,u in power.items()}
result['speed_limit_fraction']=float(np.mean(np.abs(v[m])>min(params['vmax'],params['vmax_s'])-.01))
result['mean_E']=float(np.mean(E[m]));result['minimum_abs_observer_angle_deg']=float(np.min(np.abs(q[m]))*180/np.pi)
result['correlation_request_actual']=float(np.corrcoef((pump+center+damp)[m],a[m])[0,1])
fig,axes=plt.subplots(4,1,figsize=(12,10),sharex=True)
axes[0].plot(t,np.abs(q)*180/np.pi,label='distance from upright');axes[0].axhline(0,color='k',lw=.5);axes[0].set_ylabel('Angle (deg)')
axes[1].plot(t,x,label='step-counted cart (m)');axes[1].plot(t,v/5,label='commanded speed / 5');axes[1].set_ylabel('Cart')
axes[2].plot(t,pump,label='energy pump');axes[2].plot(t,center+damp,label='centering + damping');axes[2].plot(t,a,label='limited command',alpha=.7);axes[2].set_ylabel('Accel (m/s²)')
axes[3].plot(t,E,label='normalized model energy');axes[3].axhline(1,color='k',linestyle='--',label='upright energy target');axes[3].set_ylabel('Model energy');axes[3].set_xlabel('Seconds after AUTO starts')
for ax in axes:ax.legend(loc='upper right');ax.grid(alpha=.2)
fig.suptitle(base.name+' — swing-up diagnostics\nObserver-based model; cart position/speed/acceleration are estimates or commands')
fig.tight_layout();fig.savefig(args.output/'swingup-cycle.png',dpi=140)
(args.output/'cycle.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
