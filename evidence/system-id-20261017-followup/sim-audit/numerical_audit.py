"""Offline reproducible checks; prints JSON, never opens a device or writes files."""
from dataclasses import asdict, replace
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from cartpole_sdk.contracts import ActionRequest
from cartpole_sdk.control.motion import stopping_distance
from cartpole_sdk.control.parameters import ControllerParameters
from cartpole_sdk.sim.backend import MujocoBackend
from cartpole_sdk.sim.config import SimulationConfig
from cartpole_sdk.sim.executor import ExecutorSimulation

ROOT = Path(__file__).resolve().parents[3]
report = ROOT / 'evidence/system-id-20261017/raw-final-inspection/final-inspect-01/report.json'
p = ControllerParameters(**json.loads(report.read_text())['result']['parameters'])
result = {'scope': 'offline mathematical/simulation audit; not hardware validation',
          'snapshot_sha256': hashlib.sha256(report.read_bytes()).hexdigest(),
          'parameters': asdict(p), 'step_responses': [], 'observer_response': []}
result['boundaries_m'] = dict(normal=p.rail-p.rail_margin, hard=p.rail-p.rail_fault_margin,
                             recovery=p.rail-p.rail_margin-p.rail_hysteresis)
result['stopping_distances'] = [dict(v=v, a=a, distance_m=float(stopping_distance(v,a,25,150)))
                               for v,a in [(1.5,0),(1.,0),(.5,0),(1.,10),(1.5,10)]]
for ticks in (4,10,20,50):
    cfg = SimulationConfig(rail_half_m=p.rail, control_steps=ticks)
    row = {'interval_ms': ticks}
    for cls in (MujocoBackend, ExecutorSimulation):
        backend = cls(cfg, **({'parameters':p} if cls is ExecutorSimulation else {}))
        obs = backend.reset(state=(0.,0.,math.pi,0.))
        backend.step(ActionRequest(obs.session_id, obs.clock_id, 1, obs.sequence, 0, ticks*1_000_000, 25.))
        row[cls.__name__] = {'truth': asdict(backend.ground_truth), 'diagnostics': asdict(backend.diagnostics)}
        backend.close()
    result['step_responses'].append(row)
for bw in (6.,30.):
    w, dt = 2*math.pi*bw, .001
    A = np.array([[1-2*w*dt,dt],[-w*w*dt,1.]])
    B = np.array([2*w*dt,w*w*dt])
    for frequency in (1.,math.sqrt(9.81/.124)/(2*math.pi),3.,5.):
        z = np.exp(1j*2*math.pi*frequency*dt)
        response = np.linalg.solve(np.eye(2)-A/z, B)
        rate = response[1]/(1j*2*math.pi*frequency)
        result['observer_response'].append(dict(bw_hz=bw, frequency_hz=frequency,
            rate_gain=float(abs(rate)), rate_phase_deg=float(np.angle(rate)*180/math.pi),
            rate_phase_delay_ms=float(-np.angle(rate)/(2*math.pi*frequency)*1000),
            angle_gain=float(abs(response[0])), angle_phase_deg=float(np.angle(response[0])*180/math.pi)))
base = SimulationConfig(control_steps=1, max_force_n=1000., max_steps=5000, rail_half_m=10.)
trajectories = []
for multiplier in (1.,4.):
    cfg = replace(base, cart_mass_kg=base.cart_mass_kg*multiplier,
        pole_mass_kg=base.pole_mass_kg*multiplier, hinge_damping=base.hinge_damping*multiplier,
        cart_damping=base.cart_damping if multiplier == 1 else .5)
    backend = MujocoBackend(cfg)
    obs = backend.reset(state=(0.,0.,2.3,1.))
    trajectory = []
    for tick in range(500):
        obs = backend.step(ActionRequest(obs.session_id,obs.clock_id,tick,obs.sequence,
            obs.available_ns,obs.available_ns+1_000_000,2*math.sin(tick*.01)))
        truth = backend.ground_truth
        trajectory.append([truth.x,truth.v,truth.theta,truth.omega])
    trajectories.append(np.array(trajectory))
    backend.close()
result['mass_cancellation_max_abs_state_difference'] = np.max(abs(trajectories[0]-trajectories[1]),axis=0).tolist()
paths = ['src/cartpole_sdk/sim/'+name+'.py' for name in ('backend','model','config','gym_env','executor','rig_gym_env')]
paths += ['src/cartpole_sdk/policies/rig_observation.py','src/cartpole_sdk/control/motion.py','src/cartpole_sdk/control/reference.py']
result['source_sha256'] = {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in paths}
print(json.dumps(result, indent=2, sort_keys=True))
