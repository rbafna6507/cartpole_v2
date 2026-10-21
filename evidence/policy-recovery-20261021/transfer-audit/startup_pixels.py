#!/usr/bin/env python3
"""Offline first-100ms encoder and independent pixel comparison; no hardware I/O.

Usage: startup_pixels.py --trial LOCAL_RUN --vision LOCAL_VISION_NDJSON --output NEW_DIR
Camera timestamps and state.received_ns must share the Jetson monotonic clock.
Uses actual vision geometry only; never reads embedded encoder comparison packets.
"""
import argparse,csv,gzip,json,math
from hashlib import sha256
from pathlib import Path
import numpy as np

def read(p):
 b=p.read_bytes();return gzip.decompress(b) if p.suffix=='.gz' else b

def stat(values):
 a=np.asarray(values,float)
 return None if not len(a) else dict(n=len(a),min=float(a.min()),max=float(a.max()),mean=float(a.mean()),sd=float(a.std()),span=float(np.ptp(a)))

def main():
 p=argparse.ArgumentParser();p.add_argument('--trial',type=Path,required=True);p.add_argument('--vision',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
 files=sorted(args.trial.glob('rig-*.jsonl*'));assert len(files)==1
 rows=[json.loads(x) for x in read(files[0]).splitlines()]
 states=[];state_keys=set();duplicates=0
 for r in rows:
  if r['type']!='state':continue
  s=r['state'];key=(s['sid'],s['unwrapped_tick'])
  if key in state_keys:duplicates+=1;continue
  state_keys.add(key);states.append(s)
 active=[s for s in states if s['flags']&2];assert active
 initial=active[0];sid=initial['sid'];t0=initial['received_ns']/1e9;b0=initial['unwrapped_us']
 srows=[]
 for s in states:
  t=(s['received_ns']/1e9)-t0
  if s['sid']==sid and -.25<=t<=.5:
   srows.append(dict(host_t_s=t,board_t_s=(s['unwrapped_us']-b0)/1e6,theta_deg=math.degrees(s['theta']),filtered_deg=math.degrees(s['angle_hat']),omega=s['omega'],x_step_m=s['x'],v_commanded=s['velocity'],a_commanded=s['acceleration'],demand=s['demand'],enabled=bool(s['flags']&2),fault=s['fault']))
 frames=[];seen=set()
 for r in [json.loads(x)for x in read(args.vision).splitlines()]:
  v=r.get('vision',{});t=v.get('t');key=(v.get('seq'),t)
  if t is None or key in seen or not -.25<=t-t0<=.5:continue
  seen.add(key)
  if not v.get('angle_valid') or v.get('stale') or v.get('pivot_px') is None or v.get('bob_px') is None:continue
  px,py=v['pivot_px'];bx,by=v['bob_px'];angle=math.degrees(math.atan2(bx-px,py-by))
  frames.append(dict(host_t_s=t-t0,frame_seq=v.get('seq'),pivot_x_px=px,pivot_y_px=py,bob_x_px=bx,bob_y_px=by,relative_bob_x_px=bx-px,relative_bob_y_px=by-py,relative_angle_deg=angle,length_px=math.hypot(bx-px,by-py),processing_ms=v.get('processing_ms'),host_read_to_result_ms=v.get('host_read_to_result_ms'),recorded_age_ms=1000*(r['host_t']-t)))
 frames.sort(key=lambda r:r['host_t_s'])
 # Preserve continuous angle changes when a quiet hanging pose straddles +/-pi.
 for data,keys in [(srows,['theta_deg','filtered_deg']),(frames,['relative_angle_deg'])]:
  for key in keys:
   unwrapped=np.rad2deg(np.unwrap(np.deg2rad([r[key]for r in data])))
   for r,value in zip(data,unwrapped):r[key.replace('_deg','_wrapped_deg')]=r[key];r[key]=float(value)
 before=[r for r in frames if r['host_t_s']<0]
 summaries=[]
 for lo,hi in [(-.25,0),(0,.04),(.04,.1),(.1,.2),(.2,.5)]:
  f=[r for r in frames if lo<=r['host_t_s']<hi];s=[r for r in srows if lo<=r['board_t_s']<hi]
  summaries.append(dict(window_s=[lo,hi],camera_frames=len(f),encoder_states=len(s),camera_angle_deg=stat([r['relative_angle_deg']for r in f]),encoder_angle_deg=stat([r['theta_deg']for r in s]),pivot_x_px=stat([r['pivot_x_px']for r in f]),relative_bob_x_px=stat([r['relative_bob_x_px']for r in f]),commanded_acceleration=stat([r['a_commanded']for r in s]),step_position=stat([r['x_step_m']for r in s])))
 args.output.mkdir(parents=True,exist_ok=False)
 for name,data in [('encoder.csv',srows),('pixels.csv',frames)]:
  with (args.output/name).open('w') as f:
   if data:w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
 report=dict(schema='cartpole-startup-pixels-v1',duplicate_board_states_ignored=duplicates,session=sid,first_enabled_state=initial,initial_40ms_states=[r for r in srows if 0<=r['board_t_s']<=.040001],windows=summaries,camera_coverage=dict(valid_frames=len(frames),prearm_frames=len(before),max_gap_ms=float(max(np.diff([r['host_t_s']for r in frames]))*1000) if len(frames)>1 else None),inputs={str(f.resolve()):sha256(f.read_bytes()).hexdigest()for f in [files[0],args.vision]},source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),limits=['Host camera-read and serial-receipt times share one clock; exposure and serial latency remain unknown.','Camera geometry is independent of the embedded encoder packet, which was never read.','Image-plane relative motion needs no metric cart calibration; it cannot prove meter-scale cart tracking.','Typical camera intervals cannot resolve individual 4ms encoder oscillations. Sparse/no frames are reported, not interpolated into evidence.','First enabled telemetry is a sampled bound, not the exact driver-enable edge.'])
 (args.output/'analysis.json').write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+'\n')
 import matplotlib;matplotlib.use('Agg');import matplotlib.pyplot as plt
 fig,ax=plt.subplots(3,1,figsize=(10,8),sharex=True)
 for key,label in [('theta_deg','raw encoder'),('filtered_deg','MCU filtered')]:ax[0].plot([r['host_t_s']for r in srows],[r[key]for r in srows],label=label)
 ct=[];ca=[];px=[];rel=[]
 for i,r in enumerate(frames):
  if i and r['host_t_s']-frames[i-1]['host_t_s']>.03:
   for target in [ct,ca,px,rel]:target.append(float('nan'))
  ct.append(r['host_t_s']);ca.append(r['relative_angle_deg']);px.append(r['pivot_x_px']);rel.append(r['relative_bob_x_px'])
 if frames:
  # Subtract only prearm medians for visual change; retain absolute values in CSV.
  reference=np.median([r['relative_angle_deg']for r in before]) if before else 0.
  encoder_reference=np.median([r['theta_deg']for r in srows if r['host_t_s']<0]) if before else 0.
  ax[0].plot(ct,np.asarray(ca)-reference+encoder_reference,'.-',label='pixel angle change, aligned prearm median')
  ax[1].plot(ct,px,'.-',label='pivot x (pixels)');ax[2].plot(ct,rel,'.-',label='bob x minus pivot x (pixels)')
 for a in ax:a.legend(fontsize=8);a.grid(alpha=.2);a.axvline(0,color='k',linestyle=':');a.axvline(.04,color='gray',linestyle=':')
 ax[0].set_ylabel('degrees');ax[1].set_ylabel('pixels');ax[2].set_ylabel('pixels');ax[2].set_xlabel('host timestamp minus first enabled telemetry receipt (s)');fig.suptitle(args.trial.name+' — image-plane startup, unknown exposure latency');fig.tight_layout();fig.savefig(args.output/'startup.png',dpi=150);plt.close(fig)
 print(json.dumps(dict(output=str(args.output),session=sid,windows=summaries),allow_nan=False))
if __name__=='__main__':main()
