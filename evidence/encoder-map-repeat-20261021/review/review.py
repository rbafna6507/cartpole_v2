"""Independent offline review: fixed order4 supplied by root, no model selection."""
import os,sys,hashlib,json,math,importlib.util
from pathlib import Path
import numpy as np
sys.dont_write_bytecode=True
ROOT=Path('/Users/rbafna/projects/cartpole_v2/evidence/encoder-tightening-20261021')
spec=importlib.util.spec_from_file_location('base',ROOT/'analyze.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
RAW=Path('/tmp/encoder-repeat-data/runs/encoder-tightening-20261021/manual-map-after-tightening-03')
OUT=Path('/tmp/encoder-repeat-review')
trial=base.load_trial(RAW)
original=[json.loads(l) for l in open('/tmp/encoder-repeat-analysis03/pairs.ndjson')]
ORDER=4

def stats(a):
 a=np.asarray(a,dtype=float)
 return dict(n=len(a),mean=float(a.mean()),median=float(np.median(a)),rms=float(np.sqrt(np.mean(a*a))),std=float(a.std()),p05=float(np.percentile(a,5)),p95=float(np.percentile(a,95)),abs_p95=float(np.percentile(abs(a),95)),max_abs=float(max(abs(a)))) if len(a) else dict(n=0)

def basis(q):
 q=np.array(q);c=[np.ones(len(q))]
 for n in range(1,ORDER+1):c.extend([np.sin(n*q),np.cos(n*q)])
 return np.column_stack(c)

def derivative(q,beta):
 q=np.array(q);y=np.ones(len(q))
 for n in range(1,ORDER+1):y+=n*beta[2*n-1]*np.cos(n*q)-n*beta[2*n]*np.sin(n*q)
 return y

def choose(rows,d):return [r for r in rows if r['mode']==0 and .05<=abs(r['encoder_rate_rad_s'])<=1 and np.sign(r['encoder_rate_rad_s'])==d]

def fit(rows):
 q=np.array([r['encoder_rad'] for r in rows]);y=np.array([r['residual_rad'] for r in rows]);b=np.floor((base.wrap(q)+math.pi)/math.radians(5)).astype(int).clip(0,71)
 cnt=np.bincount(b,minlength=72);w=1/np.sqrt(cnt[b]);x=basis(q)
 return np.linalg.lstsq(x*w[:,None],y*w,rcond=None)[0]

def errors(rows,beta):return base.wrap(np.array([r['residual_rad'] for r in rows])-basis([r['encoder_rad'] for r in rows])@beta)

def score(rows,beta):
 err=errors(rows,beta);near=np.array([abs(r['camera_rad'])<=math.radians(15) for r in rows])
 return dict(all_deg=stats(np.degrees(err)),near_image_upright15deg=stats(np.degrees(err[near])))

train=choose(original,1);held=choose(original,-1);beta=fit(train)
lag_sensitivity=[]
for lag in [-.217,-.167,-.117,-.067,-.017,0.,.033,.083,.133,.183]:
 rows=base.paired(trial,lag);tr=choose(rows,1);te=choose(rows,-1);b=fit(tr)
 lag_sensitivity.append(dict(lag_s=lag,training_only_refit=score(tr,b),opposite_frozen_original=score(te,beta),opposite_training_refit=score(te,b),
  predicted_image_angle_at_saved533_deg=float(np.degrees(basis([0])@b)[0])))
by_bin=[]
for c in np.arange(-177.5,180,5):
 entry=dict(center_encoder_deg=float(c))
 for d,rows in [(1,train),(-1,held)]:
  rr=[r for r in rows if abs(float(base.wrap(r['encoder_rad']-math.radians(c))))<math.radians(2.5)]
  if rr:entry[str(d)]=dict(n=len(rr),residual_deg=stats(np.degrees([r['residual_rad'] for r in rr])),corrected_deg=stats(np.degrees(errors(rr,beta))),omega=float(np.mean([r['encoder_rate_rad_s'] for r in rr])),q=float(np.mean([r['encoder_rad'] for r in rr])))
 if '1' in entry and '-1' in entry:
  entry['negative_minus_positive_deg']=entry['-1']['corrected_deg']['median']-entry['1']['corrected_deg']['median']
 by_bin.append(entry)
matched=[b for b in by_bin if 'negative_minus_positive_deg' in b]
# Diagnose, do not calibrate: dynamic direction discrepancy can combine latency
# and true directional/load effects. No lag selected from these held-out errors.
x=np.array([b['-1']['omega']-b['1']['omega'] for b in matched]);y=np.radians([b['negative_minus_positive_deg'] for b in matched])
coef=np.linalg.lstsq(np.column_stack([np.ones(len(x)),x]),y,rcond=None)[0]
near=[]
for d,rows in [(1,train),(-1,held)]:
 rr=[r for r in rows if abs(r['camera_rad'])<=math.radians(3)]
 q=np.array([r['encoder_rad'] for r in rr]);cam=np.array([r['camera_rad'] for r in rr]);fit_up=np.polyfit(cam,q,1)
 near.append(dict(direction=d,n=len(rr),encoder_at_image_zero_rad=float(fit_up[1]),native_count_at_image_zero=float(533+fit_up[1]*4096/(2*math.pi)),
  angular_rate_rad_s=stats([r['encoder_rate_rad_s'] for r in rr]),camera_deg=stats(np.degrees(cam)),camera_encoder_offset_deg=stats(np.degrees(cam-q))))
# Raw marker geometry: pivot and length are independent from the encoder model.
cam_by_seq={c['seq']:c for c in trial['camera']}
geometry={};geometry_rows=[]
for d,rows in [(1,train),(-1,held)]:
 cc=[cam_by_seq[r['camera_seq']] for r in rows];angle=np.array([c['angle'] for c in cc]);length=np.array([c['length'] for c in cc])
 px=np.array([c['pivot_x'] for c in cc]);py=np.array([c['pivot_y'] for c in cc]);dx=length*np.sin(angle);dy=-length*np.cos(angle)
 # Centered ellipse is a geometric diagnostic, not an angle correction model.
 bins=np.floor((base.wrap(angle)+math.pi)/math.radians(5)).astype(int).clip(0,71);counts=np.bincount(bins,minlength=72);weight=1/np.sqrt(counts[bins])
 X=np.column_stack([dx*dx,2*dx*dy,dy*dy]);a=np.linalg.lstsq(X*weight[:,None],weight,rcond=None)[0]
 eig=np.linalg.eigvalsh([[a[0],a[1]],[a[1],a[2]]]);ratio=math.sqrt(eig.max()/eig.min()) if eig.min()>0 else None
 radial_pred=1/np.sqrt(a[0]*np.sin(angle)**2-2*a[1]*np.sin(angle)*np.cos(angle)+a[2]*np.cos(angle)**2)
 medianpx=np.median(px);medianpy=np.median(py)
 # Recomputing against a fixed pivot quantifies observed centroid wandering.
 fixedangle=np.arctan2(dx+px-medianpx,-dy-py+medianpy)
 result=dict(pivot_x_px=stats(px),pivot_y_px=stats(py),length_px=stats(length),
  centered_ellipse_axis_ratio=ratio,centered_ellipse_radial_residual_px=stats(length-radial_pred),
  affine_axis_distortion_max_deg=None if ratio is None else float(np.degrees(np.arctan((ratio-1)/(2*np.sqrt(ratio))))),
  measured_vs_fixed_pivot_angle_delta_deg=stats(np.degrees(base.wrap(angle-fixedangle))))
 geometry[str(d)]=result
 for center in np.arange(-172.5,180,15):
  mask=abs(base.wrap(angle-math.radians(center)))<math.radians(7.5)
  if mask.any():geometry_rows.append(dict(direction=d,camera_angle_deg=float(center),n=int(mask.sum()),length_median_px=float(np.median(length[mask])),pivot_x_median_px=float(np.median(px[mask])),pivot_y_median_px=float(np.median(py[mask]))))
# Old stationary captures are a transportability check; no re-anchoring or fitting.
stationary=[];stationary_sources=[]
for name in ['upright-check-02','upright-check-03']:
 p=Path('/tmp/post-tightening-data/runs/encoder-tightening-20261021')/name
 if not p.exists():continue
 t=base.load_trial(p);stationary_sources.extend(t['sources']);native=base.circular_summary([i['encoder_raw'] for i in t['infos'] if type(i.get('encoder_raw')) is int],4096)
 c=base.circular_summary([c['angle'] for c in t['camera']]);q=float(base.wrap((native['median']-533)*2*math.pi/4096));pred=float(base.wrap(q+(basis([q])@beta)[0]))
 stationary.append(dict(name=name,native=native,camera=c,predicted_camera_deg=float(np.degrees(pred)),prediction_error_deg=float(np.degrees(base.wrap(c['median']-pred))),
  pivot=[float(np.median([c[k] for c in t['camera']])) for k in ['pivot_x','pivot_y']],frame_caution='Earlier capture; camera orientation/detector setup may differ, so failure is evidence against immediate transfer, not encoder-only drift proof.'))
report=dict(order=ORDER,order_selection='Fixed in advance by root first-direction cross-validation; review did not choose harmonics using held-out direction.',
 coefficients_rad=beta.tolist(),train=score(train,beta),opposite=score(held,beta),derivative=stats(derivative(np.linspace(-math.pi,math.pi,4097),beta)),
 predicted_camera_at_saved533_deg=float(np.degrees((basis([0])@beta)[0])),lag_sensitivity=lag_sensitivity,
 lag_interpretation='Sensitivity diagnostics are not additional independent validation and do not select deployment lag. Source/receipt timestamps do not bound image-exposure delay.',
 direction_bin_difference_deg=stats([b['negative_minus_positive_deg'] for b in matched]),direction_bins=by_bin,
 direction_speed_regression=dict(intercept_deg=float(np.degrees(coef[0])),omega_difference_coefficient_s=float(coef[1]),residual_deg=stats(np.degrees(y-np.column_stack([np.ones(len(x)),x])@coef))),
 image_upright_crossings=near,geometry=geometry,geometry_by_camera_angle=geometry_rows,earlier_stationary_transfer=stationary,
 no_hardware_or_repository_changes=True,hardware_accepted=False,calibration_accepted=False)
sources=[RAW/'report.json',RAW/'vision.ndjson',RAW/'vision-report.json',*RAW.glob('rig*.jsonl'),Path('/tmp/encoder-repeat-analysis03/report.json'),Path('/tmp/encoder-repeat-analysis03/pairs.ndjson'),ROOT/'analyze.py',Path(__file__),Path('/tmp/000158.png'),Path('/tmp/000081.png')]
sources.extend(stationary_sources)
report['source_hashes']=[dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sources]
(OUT/'review.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
os.environ['MPLCONFIGDIR']=str(OUT/'mpl-cache')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
fig,axes=plt.subplots(2,2,figsize=(13,9),layout='constrained')
for d,rows in [(1,train),(-1,held)]:
 q=np.degrees([r['encoder_rad'] for r in rows]);res=np.degrees([r['residual_rad'] for r in rows]);e=np.degrees(errors(rows,beta))
 axes[0,0].scatter(q,res,s=5,alpha=.3,label=f'Direction {d:+d}')
 axes[0,1].scatter(q,e,s=5,alpha=.3,label=f'Direction {d:+d}')
 g=[r for r in geometry_rows if r['direction']==d]
 axes[1,0].plot([x['camera_angle_deg'] for x in g],[x['length_median_px'] for x in g],'.-',label=f'Direction {d:+d}')
q=np.linspace(-math.pi,math.pi,721);axes[0,0].plot(np.degrees(q),np.degrees(basis(q)@beta),c='black',label='Fixed order4 trained + direction')
axes[0,0].set(xlabel='Encoder angle (deg)',ylabel='Camera − encoder (deg)')
axes[0,1].set(xlabel='Encoder angle (deg)',ylabel='Residual after frozen curve (deg)')
axes[1,0].set(xlabel='Raw camera angle (deg)',ylabel='Marker length median (px)')
axes[1,1].plot([x['lag_s']*1000 for x in lag_sensitivity],[x['opposite_frozen_original']['all_deg']['rms'] for x in lag_sensitivity],'.-',label='Original coefficients fixed')
axes[1,1].plot([x['lag_s']*1000 for x in lag_sensitivity],[x['opposite_training_refit']['all_deg']['rms'] for x in lag_sensitivity],'.-',label='Refit + direction only at each lag')
axes[1,1].axvline(-17,color='gray',ls=':');axes[1,1].set(xlabel='Timing proxy (ms); no lag selected',ylabel='Opposite direction RMS (deg)')
for ax in axes.ravel():ax.grid(alpha=.2);ax.legend(fontsize=8)
fig.suptitle('Independent review: within-run curve consistency does not establish stationary transfer')
fig.savefig(OUT/'review.png',dpi=170);plt.close(fig)
print(json.dumps({k:report[k] for k in ['train','opposite','predicted_camera_at_saved533_deg','direction_bin_difference_deg','direction_speed_regression','image_upright_crossings','geometry','earlier_stationary_transfer']},indent=2))
