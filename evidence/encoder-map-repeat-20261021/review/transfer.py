"""Frozen rotation03 model challenge; no coefficient, zero or lag fitting."""
import os,sys,json,math,hashlib,importlib.util,csv
from pathlib import Path
import numpy as np
sys.dont_write_bytecode=True
OUT=Path('/tmp/encoder-repeat-review');ROOT=Path('/Users/rbafna/projects/cartpole_v2/evidence/encoder-tightening-20261021')
spec=importlib.util.spec_from_file_location('base',ROOT/'analyze.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
MODEL=json.load(open(OUT/'review.json'));BETA=np.array(MODEL['coefficients_rad']);ORDER=MODEL['order']
def mapped(q):
 q=np.asarray(q,dtype=float);y=q+BETA[0]
 for n in range(1,ORDER+1):y=y+BETA[2*n-1]*np.sin(n*q)+BETA[2*n]*np.cos(n*q)
 return base.wrap(y)
def stats(x):
 x=np.asarray(x,dtype=float)
 return dict(n=len(x),mean=float(np.mean(x)),median=float(np.median(x)),std=float(np.std(x)),rms=float(np.sqrt(np.mean(x*x))),abs_p95=float(np.percentile(abs(x),95)),min=float(np.min(x)),max=float(np.max(x))) if len(x) else dict(n=0)
def score(rows,anchor=None):
 q=np.array([r['encoder_rad'] for r in rows]);cam=np.array([r['camera_rad'] for r in rows]);error=base.wrap(cam-mapped(q));raw=base.wrap(cam-q)
 d=dict(paired_samples=len(rows),raw_camera_minus_encoder_deg=stats(np.degrees(raw)),camera_minus_frozen_model_deg=stats(np.degrees(error)),encoder_angle_deg=stats(np.degrees(q)),raw_camera_angle_deg=stats(np.degrees(cam)),encoder_rate_rad_s=stats([r['encoder_rate_rad_s'] for r in rows]))
 if anchor is not None:d['previously_known_upright_anchored_camera_minus_raw_encoder_deg']=stats(np.degrees(base.wrap(cam-anchor-q)))
 return d

def main():
 sources=[OUT/'review.json',ROOT/'analyze.py',Path(__file__)];quiet=[]
 for name,path in [('rotation03',Path('/tmp/encoder-repeat-analysis03/report.json')),('upright04',Path('/tmp/encoder-upright-check04-analysis/report.json'))]:
  d=json.load(open(path));sources.append(path);origin=d['holds'][0]['start_s']
  for i,h in enumerate(d['holds']):
   native=h['native_info_counts'];cam=h['camera_image_angle_rad'];q=float(base.wrap((native['median']-533)*2*math.pi/4096));pred=float(mapped([q])[0]);err=float(np.degrees(base.wrap(cam['median']-pred)))
   quiet.append(dict(trial=name,index=i,start_s=h['start_s']-origin,duration_s=h['duration_s'],native_counts=native['median'],state_counts=h['reconstructed_state_counts']['median'],camera_deg=float(np.degrees(cam['median'])),camera_std_deg=float(np.degrees(cam['std'])),frozen_camera_prediction_deg=float(np.degrees(pred)),camera_minus_frozen_model_deg=err,qualified=h['stationary_comparison_qualified'],encoder_qualified=h['encoder_stationary_qualified'],camera_qualified=h['camera_stationary_qualified'],pivot_x_px=h['camera_pivot_x_px']['median'],pivot_y_px=h['camera_pivot_y_px']['median'],length_px=h['marker_length_px']['median'],native_n=native['n'],camera_n=cam['n']))
 prior_path=ROOT/'analysis-reference533-complete/report.json';prior=json.load(open(prior_path));sources.append(prior_path);anchor=prior['upright_anchor']['camera_image_angle_rad']['median'];auto=[];plotrows=[]
 for name in ['ref533-bw8-auto25-01','ref533-bw8-auto25-02']:
  trial=base.load_trial(Path('/tmp/post-tightening-data/runs/encoder-tightening-20261021')/name);sources.extend(trial['sources']);p=next(p for p in prior['trials'] if p['trial']==name);lo,hi=p['postcapture_windows']['after_2s']['window_host_s'];pairs=base.paired(trial,-.017);cc={c['seq']:c for c in trial['camera']};rows=[r for r in pairs if lo<=r['encoder_query_host_s']<=hi and r['mode']==3];near=[r for r in rows if abs(base.wrap(r['camera_rad']-anchor))<=math.radians(15) and abs(r['encoder_rate_rad_s'])<=.3]
  full=[r for r in pairs if r['mode'] in [2,3]];geometry={k:stats([cc[r['camera_seq']][k] for r in rows]) for k in ['pivot_x','pivot_y','length']};sensitivity=[]
  for lag in [-.067,-.027,-.017,-.007,0,.033]:
   rr=[r for r in base.paired(trial,lag) if lo<=r['encoder_query_host_s']<=hi and r['mode']==3]
   sensitivity.append(dict(lag_s=lag,**score(rr,anchor)))
  auto.append(dict(trial=name,window_host_s=[lo,hi],seconds_after_native_capture=2,native_BAL_duration_s=p['postcapture_windows']['entire_first_BAL']['native_bal_observed']['longest_continuous_s'],all_AUTO=score(full,anchor),postcapture_after2s=score(rows,anchor),near_upright15deg_and_rate_le_0p3=score(near,anchor),geometry=geometry,camera_filters=trial['filter_report'],clock=trial['clock'],timing_sensitivity=sensitivity,prior_same_view_upright_anchor_rad=anchor))
  plotrows.append((name,lo,rows))
 bridge_a=quiet[3];bridge_b=quiet[4]
 report=dict(method='Order4 coefficients frozen from rotation03 positive moving direction, lag fixed−17ms. No fitting, model selection or re-anchoring against these records. Raw camera angle is an image-coordinate proxy, not independently calibrated gravity.',quiet_holds=quiet,
  quiet_interpretation='No qualified upright pause was identified inside rotation03. Final03 and initial04 hanging counts agree; camera medians change only0.032°. Those hanging windows fail strict camera stationarity, so their medians are diagnostic. Earlier qualified midpoint03 hanging fits well. This rejects a single abrupt03→04 zero shift explanation but does not identify the physical mechanism.',
  between03_and04_hanging=dict(native_count_shift=bridge_b['native_counts']-bridge_a['native_counts'],camera_change_deg=float(np.degrees(base.wrap(math.radians(bridge_b['camera_deg']-bridge_a['camera_deg'])))),frozen_error_change_deg=bridge_b['camera_minus_frozen_model_deg']-bridge_a['camera_minus_frozen_model_deg'],both_camera_stationarity_qualified=False),
  historical_AUTO=auto,geometry_caveat='Earlier AUTO raw image zero has a user upright anchor−0.619085°. Sweep03 camera view/pivot later changed slightly. Raw model error is therefore a cross-recording transport test, not pure encoder error. The earlier anchor is reported only as the already-existing raw encoder comparator; no zero was estimated from AUTO or applied to the candidate.',
  outcome='Do not apply the frozen curve. Good opposite-direction performance within one manual sweep does not transfer to stationary upright or prior successful hands-off BAL. Neither model failure nor contact05 alone proves magnet/coupling, hand-load, perspective, or timing causation.',hardware_accepted=False,calibration_accepted=False)
 report['source_hashes']=[dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sources]
 (OUT/'transfer.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
 with (OUT/'quiet03-04.csv').open('w') as f:
  writer=csv.DictWriter(f,fieldnames=list(quiet[0]));writer.writeheader();writer.writerows(quiet)
 os.environ['MPLCONFIGDIR']=str(OUT/'mpl-cache');import matplotlib;matplotlib.use('Agg');import matplotlib.pyplot as plt
 fig,axes=plt.subplots(2,2,figsize=(13,8),layout='constrained')
 for col,(name,origin,rows) in enumerate(plotrows):
  for key,label in [('encoder_rad','Raw encoder'),('camera_rad','Raw camera')]:
   x=[];y=[];last=None
   for r in rows:
    if last and (r['host_s']-last['host_s']>.075 or r['segment']!=last['segment']):x.append(np.nan);y.append(np.nan)
    x.append(r['host_s']-origin);y.append(math.degrees(r[key]));last=r
   axes[0,col].plot(x,y,label=label,lw=.7)
  x=[];y=[];e=[];last=None
  for r in rows:
   if last and (r['host_s']-last['host_s']>.075 or r['segment']!=last['segment']):x.append(np.nan);y.append(np.nan);e.append(np.nan)
   pred=float(mapped([r['encoder_rad']])[0]);x.append(r['host_s']-origin);y.append(math.degrees(pred));e.append(math.degrees(float(base.wrap(r['camera_rad']-pred))));last=r
  axes[0,col].plot(x,y,label='Frozen rotation03 curve',lw=.7);axes[1,col].plot(x,e,label='Camera − frozen curve',lw=.7);axes[0,col].set_title(name);axes[1,col].set_xlabel('Seconds after postcapture +2s window start')
 for ax in axes.flat:ax.grid(alpha=.2);ax.legend(fontsize=8);ax.set_ylabel('Degrees')
 fig.suptitle('Frozen sweep curve fails prior hands-off BAL transfer\nCamera view changed slightly; no zero adjustment or model refit applied',fontsize=13);fig.savefig(OUT/'historical-auto-transfer.png',dpi=170);plt.close(fig)
 print(json.dumps(dict(quiet_holds=quiet,between03_and04_hanging=report['between03_and04_hanging'],auto=[dict(trial=a['trial'],postcapture=a['postcapture_after2s'],near_low_speed=a['near_upright15deg_and_rate_le_0p3']) for a in auto]),indent=2))
if __name__=='__main__':main()
