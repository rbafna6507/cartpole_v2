#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=1.26,<3", "mujoco>=3,<4", "matplotlib>=3.9,<4"]
# ///
"""Compare sampled-acceleration and velocity-endpoint input reconstruction.
No physical parameters, optical map or initial pole states are fitted. The
velocity signal is commanded governor velocity, not measured physical velocity.
"""
import argparse
from dataclasses import asdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
import numpy as np

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def metric(e):
 e=np.asarray(e,float);return dict(samples=len(e),rms=float(np.sqrt(np.mean(e*e))),p95_abs=float(np.quantile(abs(e),.95)),max_abs=float(max(abs(e))))
def angular(e):return dict(unit='deg',**metric(np.rad2deg(np.arctan2(np.sin(e),np.cos(e)))))

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo',type=Path,required=True);p.add_argument('--audit',type=Path,required=True);p.add_argument('--backend',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
 root=args.repo.resolve();out=args.output.resolve()
 if out.exists():p.error('new output directory required')
 sys.path.insert(0,str(root/'src'))
 from cartpole_sdk.contracts import ActionRequest
 from cartpole_sdk.sim import MujocoBackend,SimulationConfig
 import mujoco
 audit=json.loads(args.audit.read_text());previous=json.loads(args.backend.read_text());config=SimulationConfig(**previous['config'])
 batch=json.loads((root/'evidence/system-id-20261017/analysis/pulse-batch-secondary-historic-offset.json').read_text());sources={x['identity']['sha256']:x for ss in batch['inputs'].values() for x in ss};runs=[];agg={}
 for run,prior in zip(audit['runs'],previous['runs']):
  assert run['source_sha256']==prior['source_sha256'];tr=run['continuous_0_1s']['trace'];source_t=np.array(tr['t_s']);source_a=np.array(tr['acceleration_m_s2']);begin=tr['predicted_t_s'][0];end=source_t[-1]
  rawpath=Path(run['optical']['source_hashes']['rig']['path']);raw=[json.loads(line) for line in gzip.open(rawpath,'rt')];states=[]
  for r in raw:
   if r.get('type')=='state' and (not states or states[-1]['unwrapped_us']!=r['state']['unwrapped_us']):states.append(r['state'])
  shift=sources[run['source_sha256']]['time_shift_s'];board=np.array([s['unwrapped_us']/1e6+shift for s in states]);xx=np.array([s['x'] for s in states]);vv=np.array([s['velocity'] for s in states]);mask=(board>=source_t[0]-1e-9)&(board<=end+1e-9)
  board=board[mask];xx=xx[mask];vv=vv[mask];assert max(np.diff(board))<.03
  initial=tuple(prior['initial_state']);methods={};times=np.array(tr['predicted_t_s'])[1:];measured=np.interp(times,source_t,tr['measured_rad']);counted=np.interp(times,board,xx)
  for method in ['sampled_acceleration','velocity_endpoint_acceleration']:
   backend=MujocoBackend(config);backend.reset(state=initial);trajectory=[[begin,*initial]];velocity_error=[];servo_error=[];force=[];accels=[];saturated=0
   for i in range(int(math.ceil((end-begin)/.001-1e-8))):
    obs=backend.observation;t=begin+obs.available_ns/1e9
    # Piecewise linear v implies interval-average a=delta(v)/delta(t).
    # Averaging over each1ms tick also handles a tick crossing a recorded endpoint.
    acceleration=float(np.interp(t,source_t,source_a)) if method=='sampled_acceleration' else float((np.interp(t+.001,board,vv)-np.interp(t,board,vv))/.001)
    request=ActionRequest(obs.session_id,obs.clock_id,i,obs.sequence,obs.available_ns,obs.available_ns+1_000_000,acceleration);backend.step(request);truth=backend.ground_truth;diag=backend.diagnostics
    trajectory.append([begin+truth.time_ns/1e9,truth.x,truth.v,truth.theta,truth.omega]);velocity_error.append(truth.v-np.interp(t+.001,board,vv));servo_error.append(diag.achieved_acceleration_m_s2-acceleration);force.append(diag.applied_force_n);accels.append(acceleration);saturated+=diag.force_saturated
   backend.close();sim=np.array(trajectory);sim[:,3]=np.unwrap(sim[:,3]);sim[:,3]+=round((initial[2]-sim[0,3])/(2*math.pi))*2*math.pi
   q=np.interp(times,sim[:,0],sim[:,3]);pos=np.interp(times,sim[:,0],sim[:,1]);error=q-measured;agg.setdefault(method,[]).extend(error)
   # Compare exactly the same eligible delivered camera frames for both methods.
   opt=run['optical'];scale=audit['optical_map']['scale_px_per_counted_m'];lag=audit['optical_map']['lag_s'];slope=opt['timing_proxy']['slope'];origin=opt['origin_board_s']
   camera=[r for r in opt['raw_points'] if r['x_px'] is not None and -.1<=r['t_s']<=1.1];ct=np.array([r['t_s'] for r in camera]);queries=origin+(ct-lag)/slope+shift;good=(queries>=begin)&(queries<=end)
   ct=ct[good];queries=queries[good];pixels=np.array([r['x_px'] for r in camera])[good]-opt['baseline']['x_px']['median'];camera_prediction=scale*np.interp(queries,sim[:,0],sim[:,1]);count_prediction=scale*np.interp(queries,board,xx)
   methods[method]=dict(scored_vs_encoder=angular(error),cart_vs_counts_mm=metric((pos-counted)*1000),max_abs_input_acceleration_m_s2=float(max(abs(np.array(accels)))),max_abs_simulated_force_n=float(max(abs(np.array(force)))),force_saturated_ticks=int(saturated),cart_acceleration_tracking_m_s2=metric(servo_error),velocity_vs_reconstructed_endpoints_m_s=metric(velocity_error),optical_position_residual_px=metric(camera_prediction-pixels),count_optical_same_support_residual_px=metric(count_prediction-pixels),trace=dict(t_s=times.tolist(),theta_rad=q.tolist(),x_m=pos.tolist(),counted_x_m=counted.tolist(),measured_theta_rad=measured.tolist()),optical_trace=dict(t_s=ct.tolist(),measured_px=pixels.tolist(),predicted_px=camera_prediction.tolist(),counted_prediction_px=count_prediction.tolist()))
   assert methods[method]['cart_acceleration_tracking_m_s2']['max_abs']<1e-10 and saturated==0
   if method=='velocity_endpoint_acceleration':assert max(abs(np.array(velocity_error)))<2e-11
  assert abs(methods['sampled_acceleration']['scored_vs_encoder']['rms']-prior['scored_vs_encoder']['rms'])<1e-10
  assert methods['sampled_acceleration']['optical_trace']['t_s']==methods['velocity_endpoint_acceleration']['optical_trace']['t_s']
  runs.append(dict(name=run['name'],role=run['role'],source_sha256=run['source_sha256'],initial_state=initial,initial_time_s=begin,final_time_s=end,source_velocity_samples=len(board),max_velocity_sample_gap_s=float(max(np.diff(board))),recorded_interval_average_acceleration_min_max_m_s2=[float(min(np.diff(vv)/np.diff(board))),float(max(np.diff(vv)/np.diff(board)))],methods=methods))
 result=dict(schema='cartpole-velocity-reconstruction-replay-v1',accepted=False,hardware_validated=False,config=asdict(config),parameters_fitted=False,initialization='Exactly the earlier audit0.1s pole state and measured count/governor-velocity cart state. No reinitialization or coefficient fit.',method='Each recorded velocity interval has average acceleration delta(v)/delta(t). Linear interpolation of velocity preserves both interval endpoints; input at each1ms backend tick is [v(t+1ms)-v(t)]/1ms. Recorded acceleration comparison is unchanged linear interpolation at tick start.',caveats=['Velocity is internal governor state, not independently measured physical cart velocity.','This is an offline reconstruction using interval endpoints, not a causal online velocity differentiator or a full firmware replay.','Velocities/counts/acceleration all originate in the same step generator; their agreement is internal consistency.','Per-frame optical comparisons use the fixed original-training pixel/count scale and proxy lag; metric scale, camera exposure time and motor force are unmeasured.','Camera support begins only when the reconstructed trajectory exists after initialization; missing raw geometry is never filled.'],aggregate={k:angular(np.array(v)) for k,v in agg.items()},runs=runs,provenance=dict(script_sha256=sha(__file__),audit_sha256=sha(args.audit),previous_backend_report_sha256=sha(args.backend),mujoco_version=mujoco.__version__,source_sha256={str(p.relative_to(root)):sha(p) for p in [root/'src/cartpole_sdk/sim/backend.py',root/'src/cartpole_sdk/sim/config.py',root/'src/cartpole_sdk/sim/model.py']}))
 out.mkdir(parents=True,exist_ok=False);(out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
 import matplotlib;matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 fig,axes=plt.subplots(6,2,figsize=(13,17),layout='constrained')
 for axrow,row in zip(axes,runs):
  ax=axrow[0];tr=row['methods']['sampled_acceleration']['trace'];t=np.array(tr['t_s'])-row['initial_time_s'];ax.plot(t,np.array(tr['counted_x_m'])*1000,label='Recorded emitted counts',color='black',lw=1.8)
  for name,label in [('sampled_acceleration','From sampled acceleration'),('velocity_endpoint_acceleration','From velocity endpoints')]:
   tr=row['methods'][name]['trace'];ax.plot(t,np.array(tr['x_m'])*1000,label=label,lw=1.3)
   op=row['methods'][name]['optical_trace'];axrow[1].plot(op['t_s'],op['predicted_px'],label=label,lw=1.3)
  op=row['methods']['velocity_endpoint_acceleration']['optical_trace'];axrow[1].scatter(op['t_s'],op['measured_px'],s=10,color='black',label='Raw pivot pixels')
  ax.set_title(row['name']);ax.set_xlabel('Seconds after initialization');ax.set_ylabel('Cart position (counted mm)');ax.grid(alpha=.2)
  axrow[1].set_title('Same-support optical comparison, frozen training map');axrow[1].set_xlabel('Seconds from pulse start (receipt proxy)');axrow[1].set_ylabel('Pivot x − pre-pulse median (px)');axrow[1].grid(alpha=.2)
 axes[0,0].legend(fontsize=8);axes[0,1].legend(fontsize=8);fig.suptitle('Input reconstruction sensitivity: no physical-parameter fitting\nVelocity endpoints reconstruct count motion; both channels remain governor quantities')
 fig.savefig(out/'input-reconstruction.png',dpi=150);plt.close(fig)
 print(json.dumps(dict(aggregate=result['aggregate'],runs=[dict(name=r['name'],methods={k:{kk:vv for kk,vv in v.items() if kk not in ['trace','optical_trace']} for k,v in r['methods'].items()}) for r in runs]),indent=2))
if __name__=='__main__':main()
