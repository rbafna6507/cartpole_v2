"""Offline contact05 review: no inferred contact timestamps and no refitting."""
import os,sys,json,math,hashlib,importlib.util
from pathlib import Path
import numpy as np
sys.dont_write_bytecode=True
OUT=Path('/tmp/encoder-repeat-review');ROOT=Path('/Users/rbafna/projects/cartpole_v2/evidence/encoder-tightening-20261021')
spec=importlib.util.spec_from_file_location('base',ROOT/'analyze.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
model=json.load(open(OUT/'review.json'));beta=np.array(model['coefficients_rad']);order=model['order']
raw=Path('/tmp/encoder-repeat-data/runs/encoder-tightening-20261021/manual-map-upright-contact-05');trial=base.load_trial(raw)
prior=json.load(open('/tmp/encoder-contact-check05-analysis/report.json'));verification04=json.load(open(OUT/'stationary04.json'))
origin=trial['host'][0];end=trial['host'][-1];pairs=base.paired(trial,-.017)
def mapped(q):
 q=np.asarray(q);y=q+beta[0]
 for n in range(1,order+1):y=y+beta[2*n-1]*np.sin(n*q)+beta[2*n]*np.cos(n*q)
 return base.wrap(y)
def stats(x):
 x=np.asarray(x,dtype=float)
 return dict(n=len(x),median=float(np.median(x)),mean=float(np.mean(x)),std=float(np.std(x)),min=float(np.min(x)),max=float(np.max(x)),rms=float(np.sqrt(np.mean(x*x))),p05=float(np.percentile(x,5)),p95=float(np.percentile(x,95))) if len(x) else dict(n=0)
def window(lo,hi):
 ss=[s for t,s in zip(trial['host'],trial['states']) if lo<=t<=hi];cc=[c for c in trial['camera'] if lo<=c['t']<=hi]
 ii=[i for i in trial['infos'] if lo<=i['received_ns']/1e9<=hi and type(i.get('encoder_raw')) is int]
 rr=[r for r in pairs if lo<=r['encoder_query_host_s']<=hi]
 native=base.circular_summary([i['encoder_raw'] for i in ii],4096);cam=base.circular_summary([c['angle'] for c in cc]);q=None if native is None else float(base.wrap((native['median']-533)*2*math.pi/4096))
 return dict(time_s=[lo-origin,hi-origin],native_info_counts=native,state_reconstructed_counts=base.circular_summary([(533+s['theta']*4096/(2*math.pi))%4096 for s in ss],4096),
  native_theta_deg=None if q is None else float(np.degrees(q)),camera_angle_deg=None if cam is None else float(np.degrees(cam['median'])),camera_angle_summary_rad=cam,
  raw_encoder_minus_camera_deg=None if q is None or cam is None else float(np.degrees(base.wrap(q-cam['median']))),
  frozen_model_camera_prediction_deg=None if q is None else float(np.degrees(mapped([q])[0])),
  frozen_model_camera_error_deg=None if q is None or cam is None else float(np.degrees(base.wrap(cam['median']-mapped([q])[0]))),
  paired_raw_encoder_minus_camera_deg=stats(np.degrees([base.wrap(r['encoder_rad']-r['camera_rad']) for r in rr])),
  paired_frozen_model_error_deg=stats(np.degrees(base.wrap(np.array([r['camera_rad'] for r in rr])-mapped([r['encoder_rad'] for r in rr])))),
  pivot_x_px=stats([c['pivot_x'] for c in cc]),pivot_y_px=stats([c['pivot_y'] for c in cc]),marker_length_px=stats([c['length'] for c in cc]),
  omega_rad_s=stats([s['omega'] for s in ss]),camera_valid_frames=len(cc),state_samples=len(ss))
def change(a,b):
 q=float(base.wrap((b['native_info_counts']['median']-a['native_info_counts']['median'])*2*math.pi/4096));c=math.radians(b['camera_angle_deg']-a['camera_angle_deg']);diff=float(base.wrap(q-c))
 return dict(encoder_shift_counts=q*4096/(2*math.pi),encoder_shift_deg=float(np.degrees(q)),raw_camera_pose_change_deg=float(np.degrees(c)),encoder_minus_camera_shift_deg=float(np.degrees(diff)),encoder_minus_camera_shift_counts=diff*4096/(2*math.pi))
epochs=[]
for i,h in enumerate(prior['holds']):
 w=window(*h['measurement_window_s']);w.update(index=i,quiet_duration_s=h['duration_s'],qualified=h['stationary_comparison_qualified'],sustained_at_least5s=h['duration_s']>=5,
  label='Observed quiet epoch; contact state unknown')
 epochs.append(w)
sustained=[e for e in epochs if e['qualified'] and e['sustained_at_least5s']]
changes=[dict(first_epoch=a['index'],second_epoch=b['index'],**change(a,b)) for a,b in zip(sustained,sustained[1:])]
first_last15=[window(origin+.1,origin+15.1),window(end-15,end)]
initial_final=change(sustained[0],sustained[-1])
for e in epochs:
 if e['native_info_counts'] and e['camera_angle_deg'] is not None:e['differential_from_first_quiet_epoch']=change(sustained[0],e)
# Non-overlapping half-second summaries give reviewable time-dependent changes,
# but must not be called support/release events without synchronized evidence.
halfseconds=[]
for lo in np.arange(origin,end,.5):
 rr=[r for r in pairs if lo<=r['encoder_query_host_s']<lo+.5]
 if not rr:continue
 halfseconds.append(dict(t_s=float(lo-origin),n=len(rr),encoder_deg=float(np.degrees(np.median([r['encoder_rad'] for r in rr]))),
  camera_deg=float(np.degrees(np.median([r['camera_rad'] for r in rr]))),
  raw_encoder_minus_camera_deg=float(np.degrees(np.median([base.wrap(r['encoder_rad']-r['camera_rad']) for r in rr])))))
sensitivity=[]
for lag in [-.117,-.067,-.017,0,.033,.083]:
 pp=base.paired(trial,lag);selection=[]
 for epoch in sustained:
  lo,hi=[origin+x for x in epoch['time_s']]
  selection.extend([r for r in pp if lo+.25<=r['encoder_query_host_s']<=hi-.25])
 sensitivity.append(dict(lag_s=lag,qualified_sustained_raw_difference_deg=stats(np.degrees([base.wrap(r['encoder_rad']-r['camera_rad']) for r in selection])),
  qualified_sustained_frozen_map_error_deg=stats(np.degrees(base.wrap(np.array([r['camera_rad'] for r in selection])-mapped([r['encoder_rad'] for r in selection]))))))
ss=trial['states'];roll=np.flatnonzero(np.diff([s['us'] for s in ss])<0)+1
report=dict(trial=trial['name'],motor_disabled_healthy_all=all(s['mode']==0 and s['flags']&3==1 and s['fault']==0 for s in ss),
 fixed_reference_counts=trial['reference'],native_info_diagnostics={k:sorted({i[k] for i in trial['infos'] if i.get(k) is not None}) for k in ['home_epoch','i2c_errors','encoder_recoveries','mag_status','encoder_conf']},
 clock=trial['clock'],camera_filters=trial['filter_report'],camera_retained_fraction=len(trial['camera'])/len(trial['raw_camera']),telemetry_gap_s=base.stats(np.diff(trial['board'])),
 camera_gap_s=base.stats(np.diff([c['t'] for c in trial['camera']])),raw_micros_rollovers_s=[float(trial['host'][i]-origin) for i in roll],
 rollover_note='uint32 MCU microseconds rolled over; SDK unwrapped_us remains continuous. This is not a sensor-reference/home-epoch change.',
 observed_quiet_epochs=epochs,sustained_quiet_epoch_changes=changes,initial_to_final_sustained_quiet=initial_final,
 fixed_first_last15s=first_last15,fixed_first_last15s_change=change(*first_last15),half_second_pair_medians=halfseconds,
 timing_sensitivity_sustained_quiet=sensitivity,reference04_last15=verification04['last15'],
 method=dict(model='Order4 coefficients loaded unchanged from review.json, fitted only on rotation03 positive direction. No refit or re-anchoring on contact05.',
  camera='Raw marker-vector angle relative to image vertical, not a calibrated gravity instrument. Source tracking is high quality but shared systematic geometry errors remain possible.',
  epochs='Quiet epochs come from existing passive analysis: low firmware rate, limited native/state/camera spread. Long means>=5s; all shorter qualifying epochs remain visible. They are not contact labels.',
  attribution='User reports3 support/release cycles but no exact events or images are available here. Temporal changes cannot establish contact causation, load magnitude, support duration, or hands-off status.',
  native_info='Native INFO and reconstructed STATE counts remain separate. encoder_raw_age_us is unchanged-value duration, not sample freshness.',
  statistics='Within-window spread is descriptive, not a confidence interval; frames and INFO counts are correlated.'),
 conclusions=dict(end_count_change_is_primarily_observed_pose_change=True,large_several_degree_contact_offset_demonstrated=False,
  frozen_static_map_still_fails=True,mechanism_identified=False,
  next_step='Preserve the failed frozen-map validation. If contact causality matters, match exact camera pose across repeated mechanically supported no-load/light-contact holds with synchronized events or images; current epochs cannot substitute for those labels.'),
 hardware_accepted=False,calibration_accepted=False)
sources=[*trial['sources'],OUT/'review.json',OUT/'stationary04.json',Path('/tmp/encoder-contact-check05-analysis/report.json'),ROOT/'analyze.py',Path(__file__)]
report['source_hashes']=[dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sources]
(OUT/'contact05.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
os.environ['MPLCONFIGDIR']=str(OUT/'mpl-cache')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
fig,axes=plt.subplots(4,1,figsize=(13,11),sharex=True,layout='constrained')
def line(ax,x,y,maxgap,segments=None,**kw):
 xx=[];yy=[]
 for i,(a,b) in enumerate(zip(x,y)):
  if i and (x[i]-x[i-1]>maxgap+1e-9 or segments is not None and segments[i]!=segments[i-1]):xx.append(np.nan);yy.append(np.nan)
  xx.append(a-origin);yy.append(b)
 ax.plot(xx,yy,**kw)
t=trial['host'];q=np.array([s['theta'] for s in ss]);cc=trial['camera'];ct=np.array([c['t'] for c in cc]);ca=np.array([c['angle'] for c in cc]);seg=[c['segment'] for c in cc]
line(axes[0],t,np.degrees(q),.03,label='Raw encoder relative533',lw=.65)
line(axes[0],ct,np.degrees(ca),.075,seg,label='Raw camera image angle',lw=.65)
line(axes[0],t,np.degrees(mapped(q)),.03,label='Frozen rotation03 map',lw=.65)
q0=math.radians(sustained[0]['native_theta_deg']);c0=math.radians(sustained[0]['camera_angle_deg'])
line(axes[1],t,np.degrees(q-q0),.03,label='Encoder change from first quiet epoch',lw=.65)
line(axes[1],ct,np.degrees(ca-c0),.075,seg,label='Camera pose change from first quiet epoch',lw=.65)
pt=np.array([r['host_s'] for r in pairs]);ps=[r['segment'] for r in pairs]
diff=np.degrees(base.wrap(np.array([r['encoder_rad']-r['camera_rad'] for r in pairs])))-sustained[0]['raw_encoder_minus_camera_deg']
line(axes[2],pt,diff,.075,ps,label='Encoder change − camera change',lw=.65)
err=np.degrees(base.wrap(np.array([r['camera_rad'] for r in pairs])-mapped([r['encoder_rad'] for r in pairs])))
line(axes[3],pt,err,.075,ps,label='Camera − frozen map',lw=.65)
for epoch in sustained:
 lo,hi=epoch['time_s']
 for ax in axes:ax.axvspan(lo,hi,color='green',alpha=.065)
 axes[2].plot([(lo+hi)/2],[epoch['differential_from_first_quiet_epoch']['encoder_minus_camera_shift_deg']],'o',color='black',ms=4)
for ax,label in zip(axes,['Angle (deg)','Change (deg)','Differential (deg)','Map error (deg)']):ax.set_ylabel(label);ax.grid(alpha=.2);ax.legend(fontsize=8,loc='best')
axes[-1].set_xlabel('Seconds from recording start; shading=observed quiet windows, not contact labels')
fig.suptitle('Contact05: final count change follows the camera-observed pole pose; frozen map still fails',fontsize=12)
fig.savefig(OUT/'contact05.png',dpi=170);plt.close(fig)
print(json.dumps(dict(initial_final=initial_final,first_last15=report['fixed_first_last15s_change'],changes=changes,
  epochs=[{k:e[k] for k in ['index','time_s','quiet_duration_s','native_theta_deg','camera_angle_deg','frozen_model_camera_error_deg','differential_from_first_quiet_epoch']} for e in epochs],
  camera_fraction=report['camera_retained_fraction'],rollovers=report['raw_micros_rollovers_s']),indent=2))
