#!/usr/bin/env python3
"""Serial observed-state balance teacher search; local nominal simulation only.

The actor is raw = clip(kx*x + kv*v + kth*atan2(sin(theta),cos(theta))
                     + kw*omega, -25,25), using only returned observations.
Truth is recorded after acting for metrics only. No physical rig API is used.

Example (one CPU thread, current venv):
  python examples/balance_teacher_search.py --output runs/NEW --seconds 15 \
    --seeds 42000 42001
  python examples/balance_teacher_search.py --output runs/NEW-CONFIRM --seconds 25 \
    --seeds 42000 42001 42002 42003 42004 42005 --candidates candidate-list.json
"""
import os
for _name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
              'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[_name] = '1'
import argparse
from dataclasses import asdict
from hashlib import sha256
import json
import math
from pathlib import Path
import subprocess
import time
import zipfile

import numpy as np
import torch
from cartpole_sdk.learning.diagnostics import diagnostic_provenance
from cartpole_sdk.learning.model_experiment import build_experiment, read_json
from cartpole_sdk.learning.ppo import TrainingEnv, experiment_identity
from cartpole_sdk.policies import HostPolicyParameters, HostRatePolicy

ROOT = Path(__file__).resolve().parents[1]
GAIN_NAMES = ('position_gain', 'velocity_gain', 'theta_gain', 'omega_gain')

def raw_acceleration(x, v, theta, omega, gains):
    """Memoryless observed-state law; returns the raw requested m/s^2."""
    angle = math.atan2(math.sin(theta), math.cos(theta))
    value = sum(float(gains[name]) * state for name, state in
                zip(GAIN_NAMES, (x, v, angle, omega)))
    return max(-25., min(25., value))

def gains(values):
    return dict(zip(GAIN_NAMES, map(float, values)))

def lqr(config, qx, damping):
    """Approximate 100 Hz acceleration plant, exact series discretization/DARE.

    Pole pivot inertia = 0.75*m*L_eff^2. Smooth friction derivative at zero
    adds tau_c/(I*velocity_scale) to viscous damping/I. Finite rate damping
    is smaller, so a few effective damping values are hypotheses, not fits.
    Delays, jerk and encoder quantization are omitted ONLY from synthesis;
    every candidate is evaluated in the complete unchanged environment.
    """
    length = config['effective_length_m']
    A = np.array([[0.,1.,0.,0.],[0.,0.,0.,0.],
                  [0.,0.,0.,1.],[0.,0.,9.81/length,-damping]])
    B = np.array([[0.],[1.],[0.],[-1/length]])
    M = np.zeros((5,5)); M[:4,:4] = A; M[:4,4:] = B
    discrete = np.eye(5); term = np.eye(5)
    for index in range(1,50):
        term = term @ (M*.01) / index
        discrete += term
    Ad, Bd = discrete[:4,:4], discrete[:4,4:]
    Q = np.diag([qx,1.,10.,1.]); R = np.array([[.1]]); P = Q.copy()
    for _ in range(10000):
        K = np.linalg.solve(R+Bd.T@P@Bd, Bd.T@P@Ad)
        new = Q+Ad.T@P@Ad-Ad.T@P@Bd@K
        if np.max(np.abs(new-P)) < 1e-10:
            break
        P = new
    return gains((-K).ravel())

def default_candidates(experiment):
    prior = {name: experiment['prior_parameters'][name] for name in GAIN_NAMES}
    candidates = [dict(name='host_prior', gains=prior, actor='host'),
                  dict(name='linear_prior', gains=prior)]
    hand = [('center_6_5_30_3',(6,5,30,3)),
            ('center_10_6_40_3',(10,6,40,3)),
            ('center_15_8_50_4',(15,8,50,4)),
            ('center_8_8_35_2',(8,8,35,2)),
            ('center_8_5_35_2',(8,5,35,2)),
            ('center_10_8_50_2',(10,8,50,2)),
            ('center_5_5_40_1',(5,5,40,1)),
            ('center_10_8_60_1',(10,8,60,1))]
    candidates += [dict(name=name,gains=gains(value)) for name,value in hand]
    for damping, qx in ((0.,20.),(0.,80.),(8.,20.),(16.,20.),(32.,20.)):
        candidates.append(dict(name=f'lqr_d{damping:g}_qx{qx:g}',
                               gains=lqr(experiment['simulation_config'],qx,damping),
                               synthesis=dict(damping=damping,Q=[qx,1,10,1],R=.1)))
    return candidates

def run_episode(experiment, candidate, seed):
    env = TrainingEnv(experiment,[seed])
    observation, _ = env.reset(options=dict(episode_seed=seed,start='upright'))
    policy = None
    if candidate.get('actor') == 'host':
        policy = HostRatePolicy(env.core.channels[:4],rate_hz=100,
            parameters=HostPolicyParameters(**experiment['prior_parameters']))
        policy.reset(env.core.session)
    trace = []; began = time.monotonic()
    try:
        while True:
            x,v,s,c,w,acc,brake = observation['state']
            theta = math.atan2(s,c)
            # This is the only actor input; ground truth is never read here.
            if policy is None:
                raw = raw_acceleration(x,v,theta,w,candidate['gains'])
            else:
                intent = policy.act(env.core.sdk_observation)
                if intent is None:
                    raise RuntimeError(policy.fault_reason)
                raw = intent.acceleration_m_s2
            observed = dict(x=float(x),v=float(v),theta=theta,omega=float(w),
                            age_s=observation['age_s'].tolist(),valid=observation['valid'].tolist())
            observation, _, terminated, truncated, _ = env.step([raw/env.action_scale])
            truth = env.core.ground_truth
            trace.append(dict(t_s=env.steps*.01,observed_before_action=observed,
                x=truth.x,v=truth.v,theta=truth.theta,omega=truth.omega,raw=raw,
                executed=env.core.diagnostics.executed_acceleration_m_s2,
                strict_balanced=abs(truth.x)<.12 and abs(truth.theta)<.15 and abs(truth.omega)<1,
                rail_braking=bool(env.core.diagnostics.rail_braking)))
            if terminated or truncated:
                break
        result = env.result(hold_seconds=5.)
        for label, rows in [('all',trace),('last5s',trace[-500:])]:
            xs=np.array([row['x'] for row in rows]); raw=np.array([row['raw'] for row in rows])
            executed=np.array([row['executed'] for row in rows])
            result[label] = dict(x_rms_m=float(np.sqrt(np.mean(xs*xs))),
                max_abs_x_m=float(np.max(np.abs(xs))),x_peak_to_peak_m=float(np.ptp(xs)),
                mean_x_m=float(np.mean(xs)),centering_margin_m=.12-float(np.max(np.abs(xs))),
                raw_action_rms=float(np.sqrt(np.mean(raw*raw))),
                raw_action_delta_rms=float(np.sqrt(np.mean(np.diff(raw)**2))) if len(raw)>1 else 0.,
                executed_acceleration_delta_rms=float(np.sqrt(np.mean(np.diff(executed)**2))) if len(executed)>1 else 0.,
                raw_action_at_limit_fraction=float(np.mean(np.abs(raw)>=24.975)),
                max_abs_theta_rad=max(abs(row['theta']) for row in rows),
                max_abs_omega_rad_s=max(abs(row['omega']) for row in rows))
        result['wall_seconds']=time.monotonic()-began
        return result, trace
    finally:
        env.close()

def aggregate(episodes):
    return dict(episodes=len(episodes),hold_successes=sum(e['hold_success'] for e in episodes),
        faults=sum(e['fault_reason'] is not None for e in episodes),
        min_balanced_fraction=min(e['balanced_fraction'] for e in episodes),
        min_final_balance_dwell_s=min(e['final_balance_dwell_s'] for e in episodes),
        max_abs_x_m=max(e['max_abs_x_m'] for e in episodes),
        worst_centering_margin_m=.12-max(e['max_abs_x_m'] for e in episodes),
        mean_x_rms_m=float(np.mean([e['all']['x_rms_m'] for e in episodes])),
        worst_last5s_x_peak_to_peak_m=max(e['last5s']['x_peak_to_peak_m'] for e in episodes),
        mean_raw_action_delta_rms=float(np.mean([e['all']['raw_action_delta_rms'] for e in episodes])),
        mean_raw_action_rms=float(np.mean([e['all']['raw_action_rms'] for e in episodes])),
        rail_braking_control_steps=sum(e['rail_braking_control_steps'] for e in episodes))

def objective(summary):
    # Strict hold and no faults take precedence; then RMS centering and margin.
    return (1000*summary['faults'] + 100*(summary['episodes']-summary['hold_successes'])
            + 10*(1-summary['min_balanced_fraction']) + summary['mean_x_rms_m']
            + .2*summary['max_abs_x_m'] + .001*summary['mean_raw_action_delta_rms'])

def write_json(path,value):
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')

def snapshot(output,profile):
    files=[ROOT/'pyproject.toml',ROOT/'uv.lock',Path(__file__),
           *sorted((ROOT/'src').rglob('*.py')),*sorted(profile.glob('*.json')),
           *sorted((ROOT/'src/cartpole_sdk').rglob('*.json')),
           *sorted((ROOT/'src/cartpole_sdk').rglob('*.xml'))]
    manifest={str(p.relative_to(ROOT)):sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()}
    with zipfile.ZipFile(output/'source.zip','x',zipfile.ZIP_DEFLATED) as archive:
        for name in manifest:
            archive.write(ROOT/name,name)
    return manifest

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--profile',type=Path,default=ROOT/'training/profiles/rl-encoder-20261017')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--seconds',type=float,choices=(15.,25.),default=15.)
    p.add_argument('--seeds',type=int,nargs='+',default=[42000,42001])
    p.add_argument('--candidates',type=Path)
    args=p.parse_args()
    if any(s not in range(42000,42006) for s in args.seeds) or len(set(args.seeds))!=len(args.seeds):
        p.error('Only unique development seeds 42000..42005 are permitted by this search')
    torch.set_num_threads(1); torch.set_num_interop_threads(1)
    read=lambda name:read_json(args.profile/(name+'.json'))[0]
    experiment=build_experiment(args.profile/'model.json',executor_parameters=read('executor-parameters'),
        observation_config=read('observation-config'),prior_parameters=read('prior-parameters'),
        development_only=True,seconds=args.seconds)
    assert experiment['executor_parameters']['jmax']==150
    assert experiment['simulation_config']['control_steps']==10
    assert experiment['simulation_config']['physics_dt_ns']==1000000
    assert experiment['simulation_config']['max_acceleration_m_s2']==25
    candidates=json.loads(args.candidates.read_text()) if args.candidates else default_candidates(experiment)
    names=[c['name'] for c in candidates]
    if len(set(names))!=len(names) or not names or any(not n.replace('_','').isalnum() for n in names):
        raise ValueError('candidate names must be unique and safe')
    for candidate in candidates:
        if set(candidate['gains'])!=set(GAIN_NAMES) or not all(math.isfinite(v) for v in candidate['gains'].values()):
            raise ValueError('all four finite gains are required')
    args.output.mkdir(parents=True,exist_ok=False)
    pins=diagnostic_provenance(); manifest=snapshot(args.output,args.profile.resolve())
    config=experiment['simulation_config']; I=.75*config['pole_mass_kg']*config['effective_length_m']**2
    recipe=dict(schema='cartpole-local-balance-teacher-search-v1',status='DEVELOPMENT_ONLY',
        hardware_accepted=False,deployable=False,simulation_only=True,randomization=None,
        seeds=args.seeds,seed_role='Repeatedly inspected development seeds; 45000+ never used',
        seconds=args.seconds,threads=1,experiment=experiment,
        experiment_sha256=experiment_identity(experiment),provenance=pins,
        source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        source_manifest=manifest,source_zip_sha256=sha256((args.output/'source.zip').read_bytes()).hexdigest(),
        candidates=candidates,formula='clip(position_gain*x + velocity_gain*v + theta_gain*atan2(sin(theta),cos(theta)) + omega_gain*omega,-25,25)',
        actor_input='Observed x,v,sin(theta),cos(theta),omega only; truth metrics after acting',
        linearization=dict(state_order=['x','v','theta','omega'],pivot_inertia=I,
            viscous_damping_rate=config['hinge_damping']/I,
            zero_velocity_damping_rate=(config['hinge_damping']+config['hinge_coulomb_friction_nm']/config['hinge_friction_velocity_scale_rad_s'])/I),
        ranking='Faults, final 5-second hold failures, strict balance fraction, then x RMS, max abs x and action changes',
        command=' '.join(__import__('sys').argv))
    write_json(args.output/'recipe.json',recipe)
    report=dict(recipe_sha256=sha256((args.output/'recipe.json').read_bytes()).hexdigest(),completed=False,candidates=[])
    began=time.monotonic()
    for candidate in candidates:
        episodes=[]; folder=args.output/candidate['name']; folder.mkdir()
        for seed in args.seeds:
            episode,trace=run_episode(experiment,candidate,seed)
            trace_path=folder/f'seed-{seed}.jsonl'
            with trace_path.open('w') as stream:
                for row in trace:stream.write(json.dumps(row,allow_nan=False)+'\n')
            episode['trajectory_path']=str(trace_path.relative_to(args.output))
            episode['trajectory_sha256']=sha256(trace_path.read_bytes()).hexdigest()
            episodes.append(episode)
        summary=aggregate(episodes)
        row=dict(**candidate,episodes=episodes,summary=summary,objective=objective(summary))
        report['candidates'].append(row)
        report['wall_seconds']=time.monotonic()-began
        write_json(args.output/'report.json',report)
        print(json.dumps(dict(name=candidate['name'],gains=candidate['gains'],**summary)),flush=True)
    if diagnostic_provenance()!=pins:
        raise RuntimeError('source/dependency changed during search')
    report['ranking']=[r['name'] for r in sorted(report['candidates'],key=lambda r:r['objective'])]
    report['completed']=True
    write_json(args.output/'report.json',report)
    best=min(report['candidates'],key=lambda row:row['objective'])
    write_json(args.output/'teacher-gains.json',dict(schema='cartpole-observed-balance-teacher-v1',
        status='DEVELOPMENT_ONLY',deployable=False,hardware_accepted=False,simulation_only=True,
        name=best['name'],gains=best['gains'],formula=recipe['formula'],input=recipe['actor_input'],
        rate_hz=100,raw_limit_m_s2=25,summary=best['summary'],
        report_sha256=sha256((args.output/'report.json').read_bytes()).hexdigest(),
        recipe_sha256=report['recipe_sha256'],script_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))
    print(json.dumps(dict(completed=True,ranking=report['ranking'],wall_seconds=report['wall_seconds'])),flush=True)

if __name__=='__main__':
    main()
