"""Frozen candidate check on passive releases; no fitting to held-out data."""
import sys,os,json,math,hashlib
from pathlib import Path
import numpy as np
sys.dont_write_bytecode=True
import transfer as review
base=review.base;OUT=review.OUT
raw=Path('/tmp/encoder-repeat-data/runs/encoder-tightening-20261021/manual-map-freefall-06');trial=base.load_trial(raw)
prior_path=Path('/tmp/encoder-freefall-check06-analysis/report.json');prior=json.load(open(prior_path));origin=trial['host'][0];tt=trial['host']-origin;ss=trial['states'];q=np.array([s['theta'] for s in ss]);omega=np.array([s['omega'] for s in ss]);pairs=base.paired(trial,-.017)
# A trajectory onset is not a directly observed hand-release timestamp. Start
# after a sustained speed increase to avoid scoring the manually held pose.
def onset(lo,hi,direction):
 for i in np.flatnonzero((tt>=lo)&(tt<=hi)&(direction*omega>=2)):
  future=(tt>=tt[i])&(tt<tt[i]+.05)
  if sum(future)>=10 and np.all(direction*omega[future]>=2):return float(tt[i])
 raise ValueError('No sustained release-like onset')
windows=[dict(name='accidental_first_drop',context='User reports accidentally knocking upright down; excluded from intended-release aggregate.',detected_onset_s=onset(43,45,-1),end_s=48,aggregate=False),
 dict(name='intentional_negative_release',context='User-reported release from negative20–30degrees; trajectory supports outward fall then damped oscillation. Exact hand-off instant unavailable.',detected_onset_s=onset(63,65,-1),end_s=75.2,aggregate=True),
 dict(name='intentional_positive_release',context='User-reported release from positive20–30degrees; trajectory supports outward fall then damped oscillation. Exact hand-off instant unavailable.',detected_onset_s=onset(87,89,1),end_s=99.6,aggregate=True)]
cc={c['seq']:c for c in trial['camera']}
def select(rows,w):return [r for r in rows if w['analysis_start_s']<=r['encoder_query_host_s']-origin<=w['end_s']]
def detailed(rows):
 d=review.score(rows);angle=np.array([r['camera_rad'] for r in rows]);bins=np.floor((base.wrap(angle)+math.pi)/math.radians(30)).astype(int).clip(0,11);d['camera_angle_counts_per30deg_bin']=np.bincount(bins,minlength=12).tolist();d['bins_with_at_least5']=sum(n>=5 for n in d['camera_angle_counts_per30deg_bin']);d['geometry']={k:review.stats([cc[r['camera_seq']][k] for r in rows]) for k in ['pivot_x','pivot_y','length']};return d
all_intended=[];plots=[]
for w in windows:
 w['analysis_start_s']=w['detected_onset_s']+.08;rows=select(pairs,w);w['all']=detailed(rows);w['moving_only_abs_rate_ge0p05']=detailed([r for r in rows if abs(r['encoder_rate_rad_s'])>=.05]);w['speed_groups']=[]
 for lo,hi in [(0,.3),(.3,1),(1,3),(3,8),(8,30)]:w['speed_groups'].append(dict(abs_rate_rad_s=[lo,hi],**detailed([r for r in rows if lo<=abs(r['encoder_rate_rad_s'])<hi])))
 w['direction_groups']={str(d):detailed([r for r in rows if d*r['encoder_rate_rad_s']>=.3]) for d in [-1,1]}
 w['timing_sensitivity']=[]
 for lag in [-.042,-.027,-.017,-.007,0,.008]:w['timing_sensitivity'].append(dict(lag_s=lag,**review.score(select(base.paired(trial,lag),w))))
 if w['aggregate']:all_intended.extend(rows);plots.append((w,rows))
quiet=[]
for i,h in enumerate(prior['holds']):
 c=h['camera_image_angle_rad'];native=h['native_info_counts'];theta=float(base.wrap((native['median']-533)*2*math.pi/4096));pred=float(review.mapped([theta])[0]);quiet.append(dict(index=i,start_s=h['start_s']-origin,duration_s=h['duration_s'],native_counts=native,encoder_theta_deg=math.degrees(theta),camera_deg=math.degrees(c['median']),camera_std_deg=math.degrees(c['std']),camera_minus_frozen_model_deg=math.degrees(float(base.wrap(c['median']-pred))),qualified=h['stationary_comparison_qualified'],pivot_x_px=h['camera_pivot_x_px']['median'],pivot_y_px=h['camera_pivot_y_px']['median'],length_px=h['marker_length_px']['median']))
report=dict(trial=trial['name'],reference_counts=trial['reference'],all_states_disabled_healthy=all(s['mode']==0 and s['flags']&3==1 and s['fault']==0 for s in ss),
 native_info_diagnostics={k:sorted({i[k] for i in trial['infos'] if i.get(k) is not None}) for k in ['home_epoch','i2c_errors','encoder_recoveries','mag_status','encoder_conf']},
 clock=trial['clock'],camera_filters=trial['filter_report'],telemetry_gap_s=base.stats(np.diff(trial['board'])),camera_gap_s=base.stats(np.diff([c['t'] for c in trial['camera']])),
 release_windows=windows,intended_release_aggregate=detailed(all_intended),quiet_holds=quiet,
 method=dict(model='Fixed order4 coefficients trained on rotation03 first moving direction. No refit, new harmonics, re-anchoring or lag selection on06.',
  timing='Primary proxy−17ms unchanged. Sensitivity−42..+8ms is descriptive, not fitted latency. Host receipt/source readback times do not establish exposure latency. Fast residuals therefore cannot be assigned entirely to a static angular error.',
  window_selection='User report separates accidental first drop from later negative and positive releases. Each scored window starts80ms after first sustained50ms outward |firmware omega|>=2rad/s in its trajectory interval. This is a conservative trajectory-defined window, not direct contact-state evidence. Assisted raising and near-release held poses are excluded from intended aggregate.',
  observability='No images/event markers were supplied with this metadata archive. Hands-free attribution follows user report and trajectory; exact hand-off/contact forces remain unobserved.',
  camera='Raw marker-vector image angle. Reject invalid/stale/low-confidence/implausible-length frames using the unchanged base loader. Never interpolate camera tracks across gaps; encoder interpolation rejects>30ms telemetry gaps.',
  support='Fast damped oscillations emphasize lower half angles. Low-speed support is much narrower than full rotation03. Do not infer a full-angle validation from aggregate RMS.',
  native_info='INFO counts and native saved reference were preserved. encoder_raw_age_us measures time since value change, not acquisition age.'),
 outcome='Frozen candidate remains unsuitable for deployment: it fails initial independent upright by about4.3degrees and improves some dynamic/hanging discrepancies without eliminating them. Fast falling residuals are strongly timing-sensitive; these windows cannot establish the required static correction or its physical cause.',
 hardware_accepted=False,calibration_accepted=False)
sources=[*trial['sources'],prior_path,OUT/'review.json',Path(__file__),Path(review.__file__),review.ROOT/'analyze.py'];report['source_hashes']=[dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sources]
(OUT/'freefall06.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
os.environ['MPLCONFIGDIR']=str(OUT/'mpl-cache');import matplotlib;matplotlib.use('Agg');import matplotlib.pyplot as plt
fig,axes=plt.subplots(3,2,figsize=(14,10),layout='constrained')
for col,(w,rows) in enumerate(plots):
 origin2=origin+w['analysis_start_s'];x=np.array([r['host_s']-origin2 for r in rows]);en=np.array([r['encoder_rad'] for r in rows]);ca=np.array([r['camera_rad'] for r in rows]);pred=review.mapped(en)
 for y,label in [(en,'Raw encoder'),(ca,'Raw camera'),(pred,'Frozen curve')]:axes[0,col].scatter(x,np.degrees(y),s=3,label=label,alpha=.65)
 axes[1,col].scatter(x,[r['encoder_rate_rad_s'] for r in rows],s=3,label='Firmware filtered rate',alpha=.65)
 for y,label in [(base.wrap(ca-en),'Camera − raw encoder'),(base.wrap(ca-pred),'Camera − frozen curve')]:axes[2,col].scatter(x,np.degrees(y),s=4,label=label,alpha=.6)
 axes[0,col].set_title(w['name'].replace('_',' ')+'\nStart '+format(w['analysis_start_s'],'.3f')+'s; fixed lag−17ms')
 axes[2,col].set_xlabel('Seconds after conservative falling-window start')
for ax in axes.flat:ax.grid(alpha=.2);ax.legend(fontsize=8)
for row,label in enumerate(['Image/encoder angle (deg)','Rate (rad/s)','Discrepancy (deg)']):axes[row,0].set_ylabel(label)
fig.suptitle('Passive06: frozen curve challenged without refitting\nAssisted raising and accidental first drop excluded; rapid-motion errors have unresolved timing contribution',fontsize=13);fig.savefig(OUT/'freefall06.png',dpi=170);plt.close(fig)
print(json.dumps(dict(windows=[dict(name=w['name'],start_s=w['analysis_start_s'],end_s=w['end_s'],all=w['all'],speed_groups=w['speed_groups'],timing_sensitivity=w['timing_sensitivity']) for w in windows],quiet_holds=quiet),indent=2))
