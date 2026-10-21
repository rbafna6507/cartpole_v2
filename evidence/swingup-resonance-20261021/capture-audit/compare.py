import sys,json,math,importlib.util,hashlib
from pathlib import Path
import numpy as np
sys.dont_write_bytecode=True
ROOT=Path('/Users/rbafna/projects/cartpole_v2');OUT=Path('/tmp/cartpole-tuning-review');spec=importlib.util.spec_from_file_location('base',ROOT/'evidence/encoder-tightening-20261021/analyze.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
def summary(a):
 a=np.array(a);return dict(n=len(a),median=float(np.median(a)),mean=float(np.mean(a)),rms=float(np.sqrt(np.mean(a*a))),min=float(min(a)),max=float(max(a))) if len(a) else dict(n=0)
reports=[];sources=[]
for name in ['bw8-auto25-01','bw8-auto25-02','bw8-auto25-03']:
 tr=base.load_trial(Path('/tmp/cartpole-tuning-resume/data/runs/encoder-tuning-resume-20261021')/name);sources.extend(tr['sources']);host=tr['host'];ss=tr['states'];pairs=base.paired(tr,-.017);mode=np.array([s['mode'] for s in ss]);first=np.flatnonzero(mode==3)[0];last=first
 while last+1<len(ss) and ss[last+1]['mode']==3:last+=1
 cap=host[first];auto=host[np.flatnonzero(np.isin(mode,[2,3]))[0]];camera={c['seq']:c for c in tr['camera']}
 def snapshot(target):
  idx=int(np.argmin(abs(host-target)));state=ss[idx];local=[r for r in pairs if abs(r['encoder_query_host_s']-target)<.06];near=min(pairs,key=lambda r:abs(r['encoder_query_host_s']-target));rows=[]
  for r in local:
   row=dict(r);row['t_relative_capture_s']=r['encoder_query_host_s']-cap;row['geometry']=camera[r['camera_seq']];rows.append(row)
  slope=None;intercept=None
  if len(local)>=4 and max(r['encoder_query_host_s'] for r in local)-min(r['encoder_query_host_s'] for r in local)>=.06 and len({r['segment'] for r in local})==1:
   times=np.array([r['encoder_query_host_s']-target for r in local]);angles=np.unwrap([r['camera_rad'] for r in local]);fit=np.polyfit(times,angles,1);slope=float(fit[0]);intercept=float(base.wrap(fit[1]))
  return dict(t_relative_capture_s=float(target-cap),native_state=state,state_sample_offset_s=float(host[idx]-target),closest_pair=near,closest_pair_offset_s=float(near['encoder_query_host_s']-target),local_camera_fit_at_target_rad=intercept,local_camera_rate_rad_s=slope,local_pairs=rows)
 stages=[snapshot(cap+dt) for dt in [-.05,0,.18,.3,.6]];rr=[r for r in pairs if cap-.1<=r['encoder_query_host_s']<=cap+.2];geom=[camera[r['camera_seq']] for r in rr];rest=base.rest_report(tr,'before_auto_rest')
 rrpost=[r for r in pairs if cap+2<=r['encoder_query_host_s']<=host[last] and r['mode']==3]
 report=dict(trial=name,capture_after_auto_s=float(cap-auto),first_balance_duration_s=float(host[last]-cap),capture_host_s=float(cap),auto_host_s=float(auto),first_BAL_state=ss[first],last_BAL_state=ss[last],next_state=ss[last+1] if last+1<len(ss) else None,parameters=tr['report']['test_parameters'],capture_stages=stages,
  early_camera_minus_encoder_deg=summary(np.degrees([r['residual_rad'] for r in rr])),capture_geometry={k:summary([c[k] for c in geom]) for k in ['pivot_x','pivot_y','length','confidence']},before_auto_rest=rest,
  postcapture_after2s_camera_minus_encoder_deg=summary(np.degrees([r['residual_rad'] for r in rrpost])),postcapture_after2s_encoder_deg=summary(np.degrees([r['encoder_rad'] for r in rrpost])),postcapture_after2s_camera_deg=summary(np.degrees([r['camera_rad'] for r in rrpost])),
  camera_filters=tr['filter_report'],fault_first_state=next((dict(s,t_after_auto_s=float(h-auto)) for h,s in zip(host,ss) if s['fault']),None))
 reports.append(report)
result=dict(frozen_lag_s=-.017,calibration_accepted=False,hardware_accepted=False,notes=['No new angle map or lag fit. Camera angles are image-vertical proxies.','Camera local rate fit uses120ms window only within a single uninterrupted camera segment.','Firmware forecasts use the counted cart state and commanded velocity, not independently measured cart motion.'],trials=reports)
sources.extend([Path(__file__),ROOT/'evidence/encoder-tightening-20261021/analyze.py',ROOT/'firmware/teensy_executor/swing_controller.h',ROOT/'firmware/teensy_executor/cart_motion.h'])
result['source_hashes']=[dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sources];(OUT/'compare.json').write_text(json.dumps(result,indent=2)+'\n')
for r in reports:
 print(r['trial'],'cap',r['capture_after_auto_s'],'duration',r['first_balance_duration_s'],'parameters', {k:r['parameters'][k] for k in ['pw','pz','pc1','pc2','bw','catch_a','jmax']})
 print('before',r['before_auto_rest']['native_info_counts_all']['median'],math.degrees(r['before_auto_rest']['camera_image_upright_rad']['median']),'geometry',r['capture_geometry'])
 for s in r['capture_stages']:
  st=s['native_state'];print('stage',round(s['t_relative_capture_s'],3),'rawdeg',round(math.degrees(st['theta']),3),'hatdeg',round(math.degrees(st['angle_hat']),3),'omega',round(st['omega'],3),'x',round(st['x'],4),'v',round(st['velocity'],3),'a',round(st['acceleration'],3),'demand',round(st['demand'],3),'camera_fit_deg',None if s['local_camera_fit_at_target_rad'] is None else round(math.degrees(s['local_camera_fit_at_target_rad']),3),'camera_rate',s['local_camera_rate_rad_s'],'closestframe_dt',s['closest_pair_offset_s'])
 print('post2',r['postcapture_after2s_camera_minus_encoder_deg']);print('fault',r['fault_first_state'])
