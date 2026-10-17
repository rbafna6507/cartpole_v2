#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=1.26,<3", "mujoco>=3,<4", "matplotlib>=3.9,<4"]
# ///
"""Replay old recorded governor inputs through actual production MujocoBackend.

Uses the existing audit's frozen parameters and causal0.1s initialization.
No firmware/executor replay is claimed; historical100Hz acceleration snapshots
are linearly interpolated at1ms and submitted as backend acceleration intent.
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
 e=np.asarray(e);return dict(samples=len(e),rms=float(np.sqrt(np.mean(e*e))),p95_abs=float(np.quantile(abs(e),.95)),max_abs=float(max(abs(e))))
def angles(e):return dict(unit='deg',**metric(np.rad2deg(np.arctan2(np.sin(e),np.cos(e)))))

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--repo',type=Path,required=True);parser.add_argument('--audit',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
 root=args.repo.resolve();out=args.output.resolve()
 if out.exists():parser.error('new output directory required')
 sys.path.insert(0,str(root/'src'))
 from cartpole_sdk.contracts import ActionRequest
 from cartpole_sdk.sim import MujocoBackend,SimulationConfig
 import mujoco
 audit=json.loads(args.audit.read_text());p=audit['frozen_parameters'];inertia=.75*.02275*p['effective_length_m']**2
 config=SimulationConfig(effective_length_m=p['effective_length_m'],hinge_damping=inertia*p['viscous_per_s'],hinge_coulomb_friction_nm=inertia*p['coulomb_rad_per_s2'],hinge_friction_velocity_scale_rad_s=.05)
 batch=json.loads((root/'evidence/system-id-20261017/analysis/pulse-batch-secondary-historic-offset.json').read_text());sources={x['identity']['sha256']:x for ss in batch['inputs'].values() for x in ss}
 rows=[];errs=[];odes=[]
 for run in audit['runs']:
  c=run['continuous_0_1s'];trace=c['trace'];source_t=np.array(trace['t_s']);source_a=np.array(trace['acceleration_m_s2']);begin=trace['predicted_t_s'][0];end=source_t[-1]
  rawpath=Path(run['optical']['source_hashes']['rig']['path']);raw=[json.loads(line) for line in gzip.open(rawpath,'rt')];states=[]
  for r in raw:
   if r.get('type')=='state' and (not states or states[-1]['unwrapped_us']!=r['state']['unwrapped_us']):states.append(r['state'])
  shift=sources[run['source_sha256']]['time_shift_s'];board=np.array([s['unwrapped_us']/1e6+shift for s in states]);xx=np.array([s['x'] for s in states]);vv=np.array([s['velocity'] for s in states])
  x0=float(np.interp(begin,board,xx));v0=float(np.interp(begin,board,vv));state=(x0,v0,*c['initial_state']);backend=MujocoBackend(config);backend.reset(state=state)
  simulated=[[begin,*state]];tracking=[];force=[];saturated=0
  for i in range(int(math.ceil((end-begin)/.001-1e-8))):
   obs=backend.observation;t=begin+obs.available_ns/1e9;acc=float(np.interp(t,source_t,source_a))
   request=ActionRequest(obs.session_id,obs.clock_id,i,obs.sequence,obs.available_ns,obs.available_ns+1_000_000,acc)
   backend.step(request);truth=backend.ground_truth;diag=backend.diagnostics
   simulated.append([begin+truth.time_ns/1e9,truth.x,truth.v,truth.theta,truth.omega]);tracking.append(diag.achieved_acceleration_m_s2-acc);force.append(diag.applied_force_n);saturated+=diag.force_saturated
  backend.close();sim=np.array(simulated);sim[:,3]=np.unwrap(sim[:,3]);sim[:,3]+=round((state[2]-sim[0,3])/(2*math.pi))*2*math.pi
  times=np.array(trace['predicted_t_s'])[1:];measured=np.interp(times,source_t,trace['measured_rad']);predicted=np.interp(times,sim[:,0],sim[:,3]);ode=np.array(trace['predicted_rad'])[1:]
  error=predicted-measured;ode_error=predicted-ode;errs.extend(error);odes.extend(ode_error)
  rows.append(dict(name=run['name'],role=run['role'],source_sha256=run['source_sha256'],initial_state=state,scored_vs_encoder=angles(error),vs_ode=angles(ode_error),cart_acceleration_tracking_m_s2=metric(tracking),max_abs_simulated_force_n=float(max(abs(np.array(force)))),force_saturated_ticks=int(saturated),cart_vs_counted_position_mm=metric((np.interp(times,sim[:,0],sim[:,1])-np.interp(times,board,xx))*1000),trace=dict(t_s=times.tolist(),measured_rad=measured.tolist(),ode_rad=ode.tolist(),mujoco_rad=predicted.tolist())))
 assert max(r['cart_acceleration_tracking_m_s2']['max_abs'] for r in rows)<1e-10
 assert all(r['force_saturated_ticks']==0 for r in rows)
 result=dict(schema='cartpole-production-backend-driven-replay-v1',accepted=False,hardware_validated=False,config=asdict(config),pivot_inertia_kg_m2=inertia,input='Historical100Hz sampled governor acceleration, linearly interpolated and held per1ms backend action; no replay of original1kHz firmware execution or hardware latency.',initialization='Frozen audit causal0.1s initial state copied unchanged; measured cart count/commanded velocity initialize simulation x/v.',aggregate_vs_encoder=angles(np.array(errs)),aggregate_vs_ode=angles(np.array(odes)),runs=rows,provenance=dict(script_sha256=sha(__file__),audit_sha256=sha(args.audit),mujoco_version=mujoco.__version__,source_sha256={str(p.relative_to(root)):sha(p) for p in [root/'src/cartpole_sdk/sim/backend.py',root/'src/cartpole_sdk/sim/config.py',root/'src/cartpole_sdk/sim/model.py',root/'src/cartpole_sdk/contracts.py']}))
 out.mkdir(parents=True,exist_ok=False);(out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
 import matplotlib;matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 fig,axes=plt.subplots(3,2,figsize=(13,9),layout='constrained')
 for ax,row in zip(axes.ravel(),rows):
  tr=row['trace'];t=np.array(tr['t_s'])-tr['t_s'][0]
  for key,label in [('measured_rad','Recorded encoder'),('ode_rad','Frozen ODE'),('mujoco_rad','Production MujocoBackend')]:ax.plot(t,np.rad2deg(np.array(tr[key])-math.pi),label=label,lw=1.2)
  ax.set_title(f"{row['name']}\nMuJoCo/encoder RMS {row['scored_vs_encoder']['rms']:.3f}°, MuJoCo/ODE {row['vs_ode']['rms']:.4f}°");ax.grid(alpha=.2);ax.set_xlabel('Seconds after initialization');ax.set_ylabel('Angle from frozen local hanging (deg)')
 axes[0,0].legend(fontsize=8);fig.suptitle('Production coupled backend replay: commanded-input assumption, no physical actuator qualification')
 fig.savefig(out/'production-backend-driven.png',dpi=150);plt.close(fig)
 print(json.dumps(dict(aggregate_vs_encoder=result['aggregate_vs_encoder'],aggregate_vs_ode=result['aggregate_vs_ode'],runs=[{k:v for k,v in r.items() if k!='trace'} for r in rows]),indent=2))
if __name__=='__main__':main()
