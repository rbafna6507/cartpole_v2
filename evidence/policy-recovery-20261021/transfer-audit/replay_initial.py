#!/usr/bin/env python3
"""Offline command-driven MuJoCo startup diagnostic; not physical validation.
Uses actual nominal profile and recorded governed acceleration, no second governor.
Both left-hold and linear interpolation expose unknown intermediate 1ms commands.
No fit, time shift, physical-parameter change, sensor correction, or hardware I/O.
"""
import argparse,csv,json,math
from dataclasses import asdict,replace
from hashlib import sha256
from pathlib import Path
import numpy as np
from cartpole_sdk.contracts import ActionRequest
from cartpole_sdk.sim.backend import MujocoBackend
from cartpole_sdk.sim.config import SimulationConfig
ROOT=Path(__file__).resolve().parents[3]
def main():
 p=argparse.ArgumentParser();p.add_argument('--pixels',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
 source=a.pixels/'encoder.csv';rows=list(csv.DictReader(source.open()));pre=[r for r in rows if float(r['board_t_s'])<0];active=[r for r in rows if 0<=float(r['board_t_s'])<=.20001]
 assert pre and active
 theta=float(np.median([float(r['theta_deg'])for r in pre]))*math.pi/180
 # Quiet prearm commanded velocity and median observer rate provide explicit
 # initial-state proxies; they are not independent physical measurements.
 initial=(float(pre[-1]['x_step_m']),float(pre[-1]['v_commanded']),theta,float(np.median([float(r['omega'])for r in pre])))
 model_path=ROOT/'training/profiles/rl-encoder-20261021/model.json';model=json.loads(model_path.read_text());base=SimulationConfig(**model['simulation_config']);config=replace(base,control_steps=1,max_steps=200)
 t=np.array([float(r['board_t_s'])for r in active]);acc=np.array([float(r['a_commanded'])for r in active]);results={}
 for mode in ['left_hold','linear_interpolation']:
  env=MujocoBackend(config);env.reset(state=initial);trace=[]
  for step in range(200):
   now=step*.001;u=float(np.interp(now,t,acc)) if mode=='linear_interpolation' else float(acc[max(0,np.searchsorted(t,now,side='right')-1)])
   obs=env.observation;request=ActionRequest(obs.session_id,obs.clock_id,step+1,obs.sequence,obs.available_ns,obs.available_ns+1000000,u);env.step(request)
   trace.append(dict(t_s=(step+1)*.001,theta_deg=math.degrees(env.ground_truth.theta),x=env.ground_truth.x,a=u,force_saturated=env.diagnostics.force_saturated))
  env.close();assert not any(r['force_saturated']for r in trace);results[mode]=trace
 report=dict(schema='cartpole-initial-command-replay-v1',initial_state=initial,initial_semantics='Prearm encoder median, final step/commanded velocity, prearm MCU omega median; no fitted initial state.',model_sha256=sha256(model_path.read_bytes()).hexdigest(),model_content_sha256=model['content_sha256'],source_csv_sha256=sha256(source.read_bytes()).hexdigest(),script_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),config=asdict(config),milestones={mode:[trace[k-1]for k in [4,10,20,40,60,100,200]]for mode,trace in results.items()},limits=['Open-loop acceleration-servo prediction driven by recorded governor acceleration, not a validated physical replay.','Acceleration between recorded frames is unknown; both interpolation assumptions are shown without tuning.','No startup motor-enable impulse, structural compliance, magnetic disturbance, physical cart tracking error, or camera exposure latency is modeled.','No policy was rerun and no governor was applied a second time.'])
 (a.output/'analysis.json').write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+'\n');(a.output/'trace.json').write_text(json.dumps(results,sort_keys=True,allow_nan=False)+'\n');print(json.dumps(report['milestones']))
if __name__=='__main__':main()
