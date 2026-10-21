"""Offline review of sealed camera/encoder campaigns; never opens hardware or exports a model."""
import argparse,json,hashlib,math
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from cartpole_sdk.identification.campaign import review_campaign, verify
from cartpole_sdk.identification.driven_validation import analyze_driven_campaigns

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 a.output.mkdir(parents=True,exist_ok=False)
 names=['gentle-training-01','gentle-training-02','coupled-training-01','coupled-validation-01']
 results=[]
 for name in names:
  root=a.input/name
  ok,why=verify(root)
  if not ok:raise ValueError(why)
  review=review_campaign(root,a.output/name)
  report=json.loads((root/'report.json').read_text())
  records=[json.loads(l) for l in (root/report['raw_log']).open()]
  states=[r['state'] for r in records if r.get('type')=='state']
  states=list({s['received_ns']:s for s in states}.values());states.sort(key=lambda s:s['received_ns'])
  st=np.array([s['received_ns']/1e9 for s in states]);angles=np.unwrap([s['theta'] for s in states])
  frames=[];seen=set()
  for line in (root/'vision.ndjson').open():
   r=json.loads(line);v=r['vision'];key=(v.get('seq'),v.get('t'))
   if key in seen:continue
   seen.add(key)
   if v.get('angle_valid') and v.get('theta_rad') is not None:frames.append(v)
  vt=np.array([v['t'] for v in frames]);va=np.array([v['theta_rad'] for v in frames])
  index=np.clip(np.searchsorted(st,vt)-1,0,len(st)-2)
  valid=(vt>=st[0])&(vt<=st[-1])&((st[index+1]-st[index])<.03)
  valid &= np.array([states[i]['fault']==0 and states[i+1]['fault']==0 for i in index])
  interp=np.interp(vt,st,angles);diff=np.arctan2(np.sin(va-interp),np.cos(va-interp))
  omega=np.interp(vt,st,[s['omega'] for s in states]);rest=valid&(np.abs(omega)<.15)
  active=np.array([s['flags']&2 and s['mode']!=14 for s in states],bool)
  times=st-st[0]
  fig,axes=plt.subplots(3,1,figsize=(12,8),sharex=True,layout='constrained')
  axes[0].plot(times,angles,'k-',lw=.7,label='Encoder, saved reference330')
  axes[0].plot(vt[valid]-st[0],(interp+diff)[valid],'.',ms=2,alpha=.65,label='Camera, hanging-based reference')
  axes[0].set_ylabel('Unwrapped angle (rad)');axes[0].legend()
  axes[1].plot(vt[valid]-st[0],np.degrees(diff[valid]),'.',ms=2);axes[1].set_ylabel('Camera minus encoder (°)')
  axes[2].plot(times,[s['x']*1000 for s in states],label='Counted cart x',color='C0');axes[2].set_ylabel('Step-count x (mm)',color='C0')
  ax=axes[2].twinx();vf=[v for v in frames if v.get('pivot_px')];ax.plot([v['t']-st[0] for v in vf],[v['pivot_px'][0] for v in vf],'.',ms=2,color='C1',alpha=.5);ax.set_ylabel('Camera pivot x (px)',color='C1')
  axes[2].set_xlabel('Jetson monotonic time relative to first encoder receipt (s)')
  for ax in axes:ax.grid(alpha=.2)
  fig.suptitle(name+' — diagnostic comparison, no fitted time/angle correction or metric cart scale')
  fig.savefig(a.output/name/'sensor-comparison.png',dpi=140);plt.close(fig)
  active_modes={str(m):int(sum(active & np.array([s['mode']==m for s in states]))) for m in sorted({s['mode'] for s in states})}
  result=dict(name=name,completed=report['completed'],failure=report.get('failure'),completed_trials=sum(t['completed'] for t in report['trials']),
   integrity_ok=ok,analysis_usable=review['analysis_usable'],blockers=review['blockers'],camera_quality=review['camera_quality'],timing=review['timing'],
   camera_valid_unique_frames=len(frames),paired_samples=int(valid.sum()),low_rate_pairs=int(rest.sum()),
   low_rate_median_camera_minus_encoder_deg=float(np.median(np.degrees(diff[rest]))) if rest.any() else None,
   paired_disagreement_rms_deg=float(np.sqrt(np.mean(np.degrees(diff[valid])**2))) if valid.any() else None,
   max_abs_counted_x_m=max(abs(s['x']) for s in states),active_mode_sample_counts=active_modes,
   i2c_errors_initial=report.get('initial_info',{}).get('i2c_errors'),
   comparison_clock='camera host-read vs encoder host-receipt, both Jetson monotonic; uncalibrated exposure/serial latency; no fitted alignment',
   low_rate_selection='abs recorded omega < 0.15 rad/s; may include turning points, not a physical-rest assertion',
   comparison_reference='Camera hanging zero and saved encoder upright330 differ; disagreements are not physical sensor accuracy. Camera 2pi branch chosen nearest encoder only for plotting.',
   manifest_sha256=hashlib.sha256((root/'manifest.json').read_bytes()).hexdigest())
  results.append(result)
  print(json.dumps({k:result[k] for k in ('name','completed','completed_trials','analysis_usable','paired_disagreement_rms_deg','low_rate_median_camera_minus_encoder_deg','blockers')}),flush=True)
 prediction=analyze_driven_campaigns([a.input/n for n in names if 'training' in n],[a.input/'coupled-validation-01'],allow_partial=True,output=a.output/'frozen-prediction')
 (a.output/'summary.json').write_text(json.dumps(dict(campaigns=results,parameters_fitted=False,model_promoted=False,hardware_accepted=False,analysis_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),indent=2)+'\n')
 print(json.dumps({'prediction_trials':{role:[(r['name'],t['id'],t['status']) for r in prediction[role] for t in r['trials']] for role in ('training','validation')}}))
if __name__=='__main__':main()
