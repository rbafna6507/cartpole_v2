#!/usr/bin/env python3
"""Offline independent image-plane evidence; no camera calibration is fitted."""
import csv, hashlib, json, math
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).with_name('balance47-run1-camera02')
VISION=ROOT/'runs/policy-confidence-20261021/hardware-live/camera-02/vision.ndjson'
a=json.loads((OUT/'analysis.json').read_text())
t0=a['first_active_state']['received_ns']/1e9;t1=a['last_active_state']['received_ns']/1e9
frames=[];seen=set()
for line in VISION.open():
 r=json.loads(line);v=r['vision'];ts=v.get('t')
 if ts is None or not t0-.2<=ts<=t1: continue
 key=(v.get('seq'),ts)
 if key in seen: continue
 seen.add(key)
 if not v.get('angle_valid') or not v.get('calibrated') or v.get('stale') or v.get('pivot_px') is None: continue
 frames.append(dict(relative_t_s=ts-t0,frame_seq=v['seq'],theta_camera_deg=math.degrees(v['theta_rad']),pivot_x_px=v['pivot_px'][0],pivot_y_px=v['pivot_px'][1],arm_length_px=v['length_px'],cart_valid=v.get('cart_valid'),recorded_age_ms=1000*(r['host_t']-ts)))
active=[r for r in frames if r['relative_t_s']>=0];before=[r for r in frames if r['relative_t_s']<0]
t=list(csv.DictReader((OUT/'telemetry.csv').open()))
sx=np.array([float(r['x_step_estimate_m']) for r in t]);st=np.array([float(r['host_receipt_t_s']) for r in t])
ct=np.array([r['relative_t_s'] for r in active]);px=np.array([r['pivot_x_px'] for r in active]);interp=np.interp(ct,st,sx)
result={
 'schema':'cartpole-independent-camera-check-v1',
 'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
 'vision_sha256':hashlib.sha256(VISION.read_bytes()).hexdigest(),
 'analysis_sha256':hashlib.sha256((OUT/'analysis.json').read_bytes()).hexdigest(),
 'session':a['first_active_state']['sid'],
 'prearm_200ms_valid_frames':len(before),
 'prearm_camera_mean_deg':float(np.mean([r['theta_camera_deg'] for r in before])),
 'prearm_pivot_x_mean_px':float(np.mean([r['pivot_x_px'] for r in before])),
 'active_valid_frames':len(active),
 'max_valid_camera_frame_gap_ms':float(np.max(np.diff(ct))*1000),
 'camera_angle_peak':max(active,key=lambda r:r['theta_camera_deg']),
 'camera_angle_trough':min(active,key=lambda r:r['theta_camera_deg']),
 'camera_pivot_leftmost':min(active,key=lambda r:r['pivot_x_px']),
 'camera_pivot_rightmost':max(active,key=lambda r:r['pivot_x_px']),
 'zero_shift_pivot_x_vs_step_estimate_correlation':float(np.corrcoef(px,interp)[0,1]),
 'metric_cart_calibration':False,
 'conclusions':[
  'Independent camera angle shows a large positive then negative excursion before the lease fault. Observed camera extrema differ from encoder extrema; they corroborate oscillation, not equal amplitude or zero calibration.',
  'The camera angle stays near its pre-arm value during the first60ms, so the initial encoder negative wiggle is not independently corroborated in amplitude.',
  'Arm-pivot image coordinates move left then right, in the same order as negative then positive step-count estimate. Pixels are uncalibrated; correlation supports shape/order, not physical meter-scale tracking or velocity.',
  'No embedded encoder packet was used. Camera host-read timestamp and serial-receipt timestamp share a clock but exposure/processing/serial timing remains unknown.',
  'No correction, camera calibration, model fitting, production edit or hardware action was performed.'
 ]}
(OUT/'camera-check.json').write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n')
with (OUT/'camera-pixels.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(frames[0]));w.writeheader();w.writerows(frames)
plot_t=[];plot_angle=[];plot_px=[]
for i,r in enumerate(frames):
 if i and r['relative_t_s']-frames[i-1]['relative_t_s']>.03:
  plot_t.append(float('nan'));plot_angle.append(float('nan'));plot_px.append(float('nan'))
 plot_t.append(r['relative_t_s']);plot_angle.append(r['theta_camera_deg']);plot_px.append(r['pivot_x_px'])
fig,ax=plt.subplots(3,1,figsize=(11,9),sharex=True,constrained_layout=True)
ax[0].plot(st,[float(r['theta_encoder_deg']) for r in t],label='Encoder (trial only)')
ax[0].plot(plot_t,plot_angle,'.-',label='Valid camera angle')
ax[0].set_ylabel('Angle (deg)');ax[0].legend()
ax[1].plot(plot_t,plot_px,'.-',color='tab:orange');ax[1].set_ylabel('Camera pivot x (pixels)')
ax[2].plot(st,sx*1000);ax[2].set_ylabel('Step estimate (mm)');ax[2].set_xlabel('Host time relative to first enabled trial telemetry (s)')
for x in ax:x.grid(alpha=.2);x.axvline(0,color='gray',ls=':');x.axvline(.51,color='red',ls=':',label='Lease fault')
fig.suptitle('Run1 independent angle / image-plane cart motion — no metric camera calibration')
fig.savefig(OUT/'camera-check.png',dpi=160)
print(json.dumps({k:result[k] for k in ['active_valid_frames','prearm_camera_mean_deg','prearm_pivot_x_mean_px','max_valid_camera_frame_gap_ms','zero_shift_pivot_x_vs_step_estimate_correlation']},indent=2))
