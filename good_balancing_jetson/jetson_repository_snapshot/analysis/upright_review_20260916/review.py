"""Read-only physical upright review; no serial access or controller changes."""
import os
os.environ.setdefault('MPLCONFIGDIR','/tmp/upright-review-mpl')
import csv,json,hashlib
from pathlib import Path
import numpy as np
from scipy.signal import savgol_filter
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
src=ROOT/'logs/run_20260916_152135.csv';ev=src.with_name(src.stem+'_events.jsonl')
rows=list(csv.DictReader(src.open()));keys=list(rows[0]);data={k:np.array([float(r[k]) for r in rows]) for k in keys};t=data['t_ms']/1000;mode=data['mode'].astype(int)
events=[json.loads(l) for l in ev.read_text().splitlines()];starts=np.where((mode[1:]==3)&(mode[:-1]==0))[0]+1
trials=[];fig,axs=plt.subplots(3,1,figsize=(11,9),sharex=True,layout='constrained');colors=plt.cm.tab10.colors
for n,i in enumerate(starts):
 j=i
 while j<len(t) and mode[j]==3:j+=1
 end=j
 while end<len(t) and mode[end] in (10,11):end+=1
 sl=slice(i,j);pre=i-1
 stats={'trial':n+1,'first_balance_s':t[i],'balance_duration_sample_s':t[j]-t[i], 'duration_resolution_s':.041,'pre_start_angle_deg':np.degrees(data['theta'][pre]),'pre_start_rate':data['theta_dot'][pre],'pre_start_x_mm':1000*data['x'][pre], 'abort_sample_angle_deg':np.degrees(data['theta'][j]),'abort_sample_x_mm':1000*data['x'][j],'abort_sample_v':data['v'][j],'abort_sample_accel':data['accel'][j],'balance_peak_accel':float(np.max(np.abs(data['accel'][sl]))),'balance_peak_v':float(np.max(np.abs(data['v'][sl]))),'recovery_peak_x_mm':1000*float(np.max(np.abs(data['x'][i:end]))),'end_mode':int(mode[end]),'return_end_x_mm':1000*data['x'][end],'balance_samples':int(j-i)}
 trials.append(stats)
 ts=t[pre:j+2]-t[i];c=colors[n]
 for ax,key,scale in zip(axs,['theta','v','accel'],[180/np.pi,1,1]):
  ax.plot(ts,data[key][pre:j+2]*scale,'.-',color=c,label=f'Trial {n+1}')
  ax.scatter(t[j]-t[i],data[key][j]*scale,marker='x',s=85,color=c)
for ax,label in zip(axs,['Angle error from stored upright (°)','Commanded cart speed (m/s)','Commanded acceleration (m/s²)']):
 ax.set_ylabel(label);ax.axhline(0,color='.6',lw=.7);ax.grid(alpha=.18)
axs[0].legend(ncol=4,fontsize=9);axs[0].set_title('Seven upright trials — × marks predictive rail abort\nTime relative to first BALANCE telemetry sample; cart motion is commanded, not measured')
axs[-1].set_xlabel('Time (s)');fig.savefig(OUT/'upright_trials.png',dpi=180);plt.close(fig)
# Long stationary hanging interval before any motion (first 10 seconds).
idle=(mode==0)&(t<10);angles=data['theta'][idle]
stationary={'samples':int(idle.sum()),'median_hanging_rad':float(np.median(angles)),'range_deg':float(np.ptp(angles)*180/np.pi),'implied_vertical_offset_deg':float((np.median(angles)+np.pi)*180/np.pi),'implied_upright_raw':3416+(np.median(angles)+np.pi)*4096/(2*np.pi)}
# Approximate model consistency from raw-angle curvature during BALANCE and return.
# Uniform 40ms interpolation + five-point quadratic derivative; not a plant identification.
segments=[]
for i in starts:
 end=i
 while end<len(t) and mode[end] in (3,10,11):end+=1
 tt=np.arange(t[i],t[end-1],.04);q=np.interp(tt,t[i:end],np.unwrap(data['theta'][i:end]));a=np.interp(tt,t[i:end],data['accel'][i:end]);
 if len(tt)<7:continue
 omega=savgol_filter(q,5,2,deriv=1,delta=.04);alpha=savgol_filter(q,5,2,deriv=2,delta=.04)
 segments.append((tt,q,omega,alpha,a))
consistency=[]
for delay in [0,.02,.04,.06,.08,.10,.12]:
 for offset in [0,np.median(angles)+np.pi]:
  xs=[];ys=[]
  for tt,q,w,alpha,a in segments:
   ac=np.interp(tt-delay,tt,a);mask=np.arange(len(tt));mask=(mask>=3)&(mask<len(tt)-3)
   xs.extend((-ac*np.cos(q-offset)/.1657756)[mask]);ys.extend((alpha-9.81*np.sin(q-offset)/.1657756+.402279*w)[mask])
  x=np.array(xs);y=np.array(ys);scale=float(x@y/(x@x));rms=lambda a:float(np.sqrt(np.mean(a*a)))
  consistency.append({'delay_s':delay,'vertical_offset_deg':float(offset*180/np.pi),'apparent_accel_scale':scale,'rmse_nominal_rad_s2':rms(y-x),'rmse_no_cart_rad_s2':rms(y),'rmse_fitted_rad_s2':rms(y-scale*x),'points':len(x)})
params={};snapshots=[]
for e in events:
 if e['direction']=='rx' and e['text'].startswith('= '):
  _,key,val=e['text'].split();params[key]=float(val)
 if e['text']=='# BALANCE':snapshots.append(dict(params))
report={'source':str(src.relative_to(ROOT)),'sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [src,ev]},'firmware':sorted(set(e['text'] for e in events if e['text'].startswith('# firmware'))),'attempts':sum(e['direction']=='tx' and e['text']=='bal' for e in events),'accepted':len(starts),'rejections':sum(e['text'].startswith('! bal rejected') for e in events),'all_start_settings_identical':all(p==snapshots[0] for p in snapshots),'parameters':snapshots[0],'trials':trials,'hanging_reference':stationary,'approximate_dynamics_checks':consistency,'timing':{'median_sample_ms':float(np.median(np.diff(t))*1000),'max_gap_ms':float(np.max(np.diff(t))*1000),'max_balance_loop_us':float(np.max(data['loop_us'][mode==3]))},'data_errors':[e for e in events if e['direction'] in ('parse_error','reader_error','telemetry_timeout','serial_lost')], 'user_observation':'User reports brief hand contact in one unspecified trial, release in most, and thinks cart moved away from falling side.','limitations':['Angle is measured; cart position/speed/acceleration are pulse-based commands.','25Hz telemetry is sparse for 0.1–0.6s trials. No exact start/rail-trigger board timestamp.','Hand release/contact timing unknown.','Curvature regression is a consistency diagnostic, not proof of motor tracking, delay or sign.']}
(OUT/'review.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'trials':trials,'hanging':stationary,'timing':report['timing'],'dynamics_best':sorted(consistency,key=lambda r:r['rmse_fitted_rad_s2'])[:4]},indent=2))
