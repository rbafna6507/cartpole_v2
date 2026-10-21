"""Frozen rotation03 model versus independent stationary verification04."""
import os,sys,json,math,hashlib,importlib.util
from pathlib import Path
import numpy as np
sys.dont_write_bytecode=True
OUT=Path('/tmp/encoder-repeat-review');ROOT=Path('/Users/rbafna/projects/cartpole_v2/evidence/encoder-tightening-20261021')
sp=importlib.util.spec_from_file_location('base',ROOT/'analyze.py');base=importlib.util.module_from_spec(sp);sp.loader.exec_module(base)
model=json.load(open(OUT/'review.json'));beta=np.array(model['coefficients_rad']);order=model['order']
def mapped(q):
 q=np.array(q);y=q+beta[0]
 for n in range(1,order+1):y+=beta[2*n-1]*np.sin(n*q)+beta[2*n]*np.cos(n*q)
 return base.wrap(y)
def stats(x):
 x=np.array(x);return dict(n=len(x),median=float(np.median(x)),mean=float(np.mean(x)),std=float(np.std(x)),min=float(min(x)),max=float(max(x)),rms=float(np.sqrt(np.mean(x*x))),p95_abs=float(np.percentile(abs(x),95))) if len(x) else dict(n=0)
path=Path('/tmp/encoder-repeat-data/runs/encoder-tightening-20261021/manual-map-upright-verification-04');tr=base.load_trial(path);origin=tr['host'][0]
lo=tr['host'][-1]-15;hi=tr['host'][-1]
ss=[s for t,s in zip(tr['host'],tr['states']) if lo<=t<=hi];cc=[c for c in tr['camera'] if lo<=c['t']<=hi];ii=[i for i in tr['infos'] if lo<=i['received_ns']/1e9<=hi]
native=base.circular_summary([i['encoder_raw'] for i in ii],4096);q=(native['median']-533)*2*math.pi/4096;cam=base.circular_summary([c['angle'] for c in cc]);pred=float(mapped([q])[0])
last15=dict(native=native,state_theta_deg=stats(np.degrees([s['theta'] for s in ss])),state_omega=stats([s['omega'] for s in ss]),camera_deg=stats(np.degrees([c['angle'] for c in cc])),
 predicted_camera_deg=float(np.degrees(pred)),frozen_map_error_deg=float(np.degrees(base.wrap(cam['median']-pred))),
 pivot_x_px=stats([c['pivot_x'] for c in cc]),pivot_y_px=stats([c['pivot_y'] for c in cc]),length_px=stats([c['length'] for c in cc]),
 healthy_disabled=all(s['mode']==0 and s['flags']&3==1 and not s['fault'] for s in ss))
lag=[]
for shift in [-.267,-.117,-.067,-.017,0,.033,.083,.233]:
 rr=[r for r in base.paired(tr,shift) if lo+.5<=r['host_s']<=hi-.5]
 err=base.wrap(np.array([r['camera_rad'] for r in rr])-mapped([r['encoder_rad'] for r in rr]))
 lag.append(dict(lag_s=shift,error_deg=stats(np.degrees(err))))
paired=base.paired(tr,-.017);binned=[]
for t in np.arange(63,75,.25):
 s=[s for ts,s in zip(tr['host'],tr['states']) if t<=ts-origin<t+.25];c=[c for c in tr['camera'] if t<=c['t']-origin<t+.25]
 if not s:continue
 q=base.circular_summary([x['theta'] for x in s])['median'];ca=base.circular_summary([x['angle'] for x in c]) if c else None
 binned.append(dict(t_s=float(t),state_native_count_median=float((533+q*4096/(2*math.pi))%4096),encoder_deg=float(np.degrees(q)),camera_n=len(c),
  camera_deg=None if ca is None else float(np.degrees(ca['median'])),omega_median=float(np.median([x['omega'] for x in s])),
  map_prediction_deg=float(np.degrees(mapped([q])[0])),map_error_deg=None if ca is None else float(np.degrees(base.wrap(ca['median']-mapped([q])[0])))))
# Compare geometry at approximately the same image-upright pose, without asserting physical gravity truth.
t3=base.load_trial(Path('/tmp/encoder-repeat-data/runs/encoder-tightening-20261021/manual-map-after-tightening-03'))
p3=base.paired(t3,-.017);byseq={c['seq']:c for c in t3['camera']};samepose=[]
for d in [1,-1]:
 rr=[r for r in p3 if abs(r['camera_rad'])<=math.radians(2) and .05<=abs(r['encoder_rate_rad_s'])<=1 and np.sign(r['encoder_rate_rad_s'])==d]
 c=[byseq[r['camera_seq']] for r in rr]
 samepose.append(dict(direction=d,n=len(c),pivot_x_px=stats([x['pivot_x'] for x in c]),pivot_y_px=stats([x['pivot_y'] for x in c]),length_px=stats([x['length'] for x in c]),camera_deg=stats(np.degrees([x['angle'] for x in c]))))
overlap=[dict(encoder_deg=float(np.degrees(r['encoder_rad'])),camera_deg=float(np.degrees(r['camera_rad'])),direction=int(np.sign(r['encoder_rate_rad_s']))) for r in p3 if .05<=abs(r['encoder_rate_rad_s'])<=1 and abs(r['encoder_rad']-(548-533)*2*math.pi/4096)<=math.radians(.5)]
report=dict(moving_observations_within_half_degree_of_stationary_encoder=overlap,last15=last15,timing_sensitivity_quiet=lag,transition_quarter_second_bins=binned,sweep_near_image_upright_geometry=samepose,
 recommendation='Reject this curve for control or calibration now: it fails independent stationary verification with fixed coefficients. Keep as an offline descriptive moving-state fit. Next validate independently repeated known-angle holds with supported versus light-contact conditions and recorded load/contact state, before collecting another unseen rotation. Do not retune order/offset on verification04 and call it a held-out pass.',
 causality='Load/coupling/magnetic response are hypotheses, not established mechanisms. Small measured marker/pivot changes make simple geometry error an unlikely complete explanation; exposure timing cannot explain a sustained quiet-pose offset. No contact-state event record is available to attribute the transition to a particular touch.')
sources=[OUT/'review.json',Path(__file__),*tr['sources'],Path('/tmp/encoder-upright-check04-analysis/report.json')]
report['source_hashes']=[dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sources]
(OUT/'stationary04.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
os.environ['MPLCONFIGDIR']=str(OUT/'mpl-cache')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
fig,axes=plt.subplots(3,1,figsize=(12,9),sharex=True,layout='constrained')
def line(ax,x,y,maxgap,segments=None,**kw):
 xx=[];yy=[]
 for i,(t,v) in enumerate(zip(x,y)):
  if i and (x[i]-x[i-1]>maxgap+1e-9 or abs(v-y[i-1])>180 or segments is not None and segments[i]!=segments[i-1]):xx.append(np.nan);yy.append(np.nan)
  xx.append(t-origin);yy.append(v)
 ax.plot(xx,yy,**kw)
line(axes[0],tr['host'],np.degrees([s['theta'] for s in tr['states']]),.030,label='Raw encoder relative533',lw=.8)
line(axes[0],tr['host'],np.degrees(mapped([s['theta'] for s in tr['states']])),.030,label='Frozen moving-sweep map prediction',lw=.8)
line(axes[0],[c['t'] for c in tr['camera']],np.degrees([c['angle'] for c in tr['camera']]),.075,[c['segment'] for c in tr['camera']],label='Independent raw camera',lw=.8)
err=np.degrees(base.wrap(np.array([r['camera_rad'] for r in paired])-mapped([r['encoder_rad'] for r in paired])))
line(axes[1],[r['host_s'] for r in paired],err,.075,[r['segment'] for r in paired],label='Camera − frozen map',lw=.8)
line(axes[2],tr['host'],[s['omega'] for s in tr['states']],.030,label='Firmware angular rate',lw=.8)
axes[0].set_ylim(-8,18);axes[0].set_ylabel('Angle (deg)');axes[1].set_ylabel('Residual (deg)');axes[2].set_ylabel('Angular rate (rad/s)');axes[2].set_xlabel('Seconds from recording start')
axes[2].set_xlim(64,124)
for ax in axes:ax.grid(alpha=.2);ax.legend(fontsize=8)
fig.suptitle('Independent stationary upright04 rejects the frozen rotation03 map')
fig.savefig(OUT/'stationary04.png',dpi=170);plt.close(fig)
print(json.dumps(dict(last15=last15,lag=lag,geometry=samepose,transition=binned),indent=2))
