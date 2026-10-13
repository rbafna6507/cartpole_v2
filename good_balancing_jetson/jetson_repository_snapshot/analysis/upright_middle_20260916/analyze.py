import os
os.environ.setdefault('MPLCONFIGDIR','/tmp/upright-review-mpl')
from pathlib import Path
import csv,json,hashlib
import numpy as np
from scipy.signal import welch
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
src=ROOT/'logs/run_20260916_153109.csv';raw=src.read_bytes();rows=list(csv.DictReader(raw.decode().splitlines()));d={k:np.array([float(r[k]) for r in rows]) for k in rows[0]};t=d['t_ms']/1000
mask=(t>=21.417)&(t<=61.121)&(d['mode']==3);middle=(t>=27)&(t<=47)&(d['mode']==3)
def metrics(m):
 o={'n':int(m.sum()),'t_start':float(t[m][0]),'t_end':float(t[m][-1])}
 for key in ['theta','theta_dot','x','v','accel']:
  a=d[key][m];scale=180/np.pi if key=='theta' else 1000 if key=='x' else 1
  o[key]={'mean':float(np.mean(a)*scale),'std':float(np.std(a)*scale),'rms':float(np.sqrt(np.mean(a*a))*scale),'min':float(a.min()*scale),'max':float(a.max()*scale),'p95_abs':float(np.quantile(abs(a),.95)*scale)}
 dt=np.diff(t[m]);jerk=np.diff(d['accel'][m])/dt;o['jerk_p95_abs']=float(np.quantile(abs(jerk),.95));o['jerk_near_limit_fraction']=float(np.mean(abs(jerk)>54))
 return o
report={'user_observation':'User reports two taps and does not think the cart was physically off center; inferred x offset must not be treated as measured physical displacement.','source':str(src.relative_to(ROOT)),'source_sha256':hashlib.sha256(raw).hexdigest(),'balanced_segment':metrics(mask),'clean_middle_27_to_47_s':metrics(middle),'windows':[]}
for lo in np.arange(22,61,5):
 m=(t>=lo)&(t<lo+5)&mask
 if m.sum():report['windows'].append(metrics(m))
for k in ['theta','x','v','accel']:
 tt=np.arange(t[middle][0],t[middle][-1],.04);y=np.interp(tt,t[middle],d[k][middle]);freq,psd=welch(y,fs=25,nperseg=min(512,len(y)),detrend='linear');indices=np.argsort(psd[freq>.05])[-3:][::-1];report.setdefault('dominant_frequencies_hz',{})[k]=freq[freq>.05][indices].tolist()
fig,axs=plt.subplots(4,1,figsize=(12,9),sharex=True,layout='constrained')
for ax,k,scale,label in zip(axs,['theta','x','v','accel'],[180/np.pi,1000,1,1],['Angle error (°)','Inferred cart x (mm)','Commanded speed (m/s)','Commanded acceleration (m/s²)']):
 ax.plot(t[mask],d[k][mask]*scale,lw=1);ax.axhline(0,color='.5',lw=.6);ax.axvspan(27,47,color='seagreen',alpha=.08);ax.set_ylabel(label);ax.grid(alpha=.2)
axs[1].axhline(135,color='red',ls='--');axs[1].axhline(-135,color='red',ls='--');axs[0].set_title('v19: 39.7 s upright episode — shaded interval excludes startup and the two user taps\nAbsolute board time; cart x/v/a are inferred or commanded, not measured');axs[-1].set_xlabel('Board time (s)');fig.savefig(OUT/'middle_balance.png',dpi=160);plt.close(fig)
# Samples immediately before recovery, for attribution rather than treating stop as steady-state.
report['last_two_seconds']=[{k:float(d[k][i]) for k in ['t_ms','mode','theta','theta_dot','x','v','accel']} for i in np.flatnonzero((t>59)&(t<61.3))]
(OUT/'metrics.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ['last_two_seconds','windows']},indent=2));print('5-second windows:');
for w in report['windows']:print(w['t_start'],w['t_end'],'angle mean/std',w['theta']['mean'],w['theta']['std'],'x mean/std',w['x']['mean'],w['x']['std'],'v rms',w['v']['rms'],'a rms',w['accel']['rms'])
