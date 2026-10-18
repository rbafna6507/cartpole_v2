#!/usr/bin/env python3
"""Exploratory observed-state swing-up teacher screen; simulation only.

Serial 100 Hz decisions / 1 ms physics / unchanged governor and jerk150.
Example: .venv/bin/python examples/swing_teacher_search.py --output runs/NEW
This is a research spike, not an SDK policy or deployable artifact. Candidate
selection repeatedly uses development52000..52005 and expanded21000..21007; no held-out claim.
"""
import os
for _name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
              'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[_name] = '1'
import argparse
from dataclasses import replace
from hashlib import sha256
import gzip
import json
import math
from pathlib import Path
import subprocess
import sys
import time
import zipfile

import numpy as np
import torch
from cartpole_sdk.learning.diagnostics import diagnostic_provenance
from cartpole_sdk.learning.model_experiment import build_experiment, read_json
from cartpole_sdk.learning.ppo import TrainingEnv, experiment_identity
from cartpole_sdk.policies import HostPolicyParameters, HostRatePolicy

ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = dict(effective_length_m=.16030387335574306, energy_gain=4.,
    swing_position_gain=40., swing_velocity_gain=2., phase_softness=2.,
    position_gain=1., velocity_gain=2., theta_gain=40., omega_gain=2.,
    capture_angle_rad=.5, capture_rate_rad_s=4., approach_angle_rad=.5,
    kick_acceleration_m_s2=1., kick_rate_rad_s=.5, kick_angle_rad=.2,
    energy_target=1., capture_projection_rad=100., energy_rate_gain=0.,
    blend_rate_rad_s=100., capture_x_m=.16, kick_override=1.,
    settled_angle_rad=0., settled_rate_rad_s=1., settled_x_m=.12, settled_v_m_s=.3,
    settled_inner_fraction=1., settled_position_gain=1., settled_velocity_gain=2.,
    settled_theta_gain=40., settled_omega_gain=2.)


def raw_acceleration(x, v, theta, omega, parameters):
    """Exploratory memoryless callable; only observed values, raw m/s^2.

    The phase, energy and switching conditions use encoder-derived theta/omega.
    Capture_projection_rad bounds the linear unstable coordinate theta+omega/sqrt(g/L).
    Energy rate gain is optional analytical feed-forward for small modeled loss.
    All constants are hypotheses evaluated in the unchanged complete simulator.
    """
    p = {**DEFAULTS, **parameters}
    theta = math.atan2(math.sin(theta), math.cos(theta))
    balance = p['position_gain']*x+p['velocity_gain']*v+p['theta_gain']*theta+p['omega_gain']*omega
    energy = .5*p['effective_length_m']/9.81*omega*omega+math.cos(theta)-p['energy_target']
    phase = math.tanh(omega*math.cos(theta)/p['phase_softness'])
    swing = (p['energy_gain']*energy*phase-p['swing_position_gain']*x
             -p['swing_velocity_gain']*v+p['energy_rate_gain']*phase)
    if abs(abs(theta)-math.pi)<p['kick_angle_rad'] and abs(omega)<p['kick_rate_rad_s']:
        swing = (p['kick_acceleration_m_s2'] if p['kick_override'] else swing+p['kick_acceleration_m_s2'])
    projected = abs(theta+omega/math.sqrt(9.81/p['effective_length_m']))
    capture = (abs(theta)<p['capture_angle_rad'] and abs(omega)<p['capture_rate_rad_s']
               and projected<p['capture_projection_rad'] and abs(x)<p['capture_x_m'])
    blend = 1. if capture else 0.
    if (not capture and theta*omega<0 and abs(omega)<p['blend_rate_rad_s']
            and p['approach_angle_rad']>p['capture_angle_rad']):
        blend = max(0.,min(1.,(p['approach_angle_rad']-abs(theta))/
                              (p['approach_angle_rad']-p['capture_angle_rad'])))
    raw=(1-blend)*swing+blend*balance
    raw,settled=settled_acceleration(x,v,theta,omega,raw,p)
    return max(-25.,min(25.,raw)), ('settled' if settled else 'capture' if blend==1 else 'blend' if blend>0 else 'swing')


def settled_acceleration(x,v,theta,omega,raw,p):
    if p['settled_angle_rad']<=0: return raw,False
    radius=max(abs(theta)/p['settled_angle_rad'],abs(omega)/p['settled_rate_rad_s'],
               abs(x)/p['settled_x_m'],abs(v)/p['settled_v_m_s'])
    blend=max(0.,min(1.,(1-radius)/max(1e-9,1-p['settled_inner_fraction'])))
    steady=p['settled_position_gain']*x+p['settled_velocity_gain']*v+p['settled_theta_gain']*theta+p['settled_omega_gain']*omega
    return (1-blend)*raw+blend*steady,blend>0


def default_candidates(experiment):
    better = dict(position_gain=1.,velocity_gain=2.,theta_gain=40.,omega_gain=2.)
    candidates = [dict(name='host_original',actor='host',parameters={}),
        dict(name='host_balance_improved',actor='host',parameters=better),
        dict(name='host_length_improved',actor='host',parameters={**better,'effective_length_m':DEFAULTS['effective_length_m']})]
    for energy, capture, rate in ((4.,.3,3.),(4.,.5,4.),(4.,.7,6.),(6.,.5,4.),(8.,.5,4.)):
        candidates.append(dict(name=f'mem_e{energy:g}_a{capture:g}_w{rate:g}'.replace('.','p'),
            actor='memoryless',parameters=dict(energy_gain=energy,capture_angle_rad=capture,
                capture_rate_rad_s=rate,approach_angle_rad=capture)))
    return candidates


def run_episode(experiment,candidate,seed,start):
    env=TrainingEnv(experiment,[seed]); observation,_=env.reset(options=dict(episode_seed=seed,start=start))
    policy=None
    reflection=candidate.get('reflection','none')
    direction=(-1. if observation['state'][0]<0 else 1.) if reflection=='initial_x' else (-1. if reflection=='negative' else 1.)
    canonical_frame='simulation:teacher-canonical-x'
    channels=env.core.channels[:4]
    if reflection!='none': channels=tuple(replace(c,frame_id=canonical_frame) for c in channels)
    if candidate['actor'] in ('host','host_schedule','host_latch'):
        policy=HostRatePolicy(channels,rate_hz=100,
            parameters=replace(HostPolicyParameters(**experiment['prior_parameters']),
                **{k:v for k,v in candidate['parameters'].items() if k in HostPolicyParameters.__dataclass_fields__}))
        policy.reset(env.core.session)
    trace=[]; first_five=None; began=time.monotonic(); transitions=[]; previous_mode=None; settled_latched=False
    try:
        while True:
            x,v,s,c,w,acc,brake=observation['state']; theta=math.atan2(s,c)
            # No simulator truth enters either actor path.
            if policy is None:
                raw,mode=raw_acceleration(float(x),float(v),theta,float(w),candidate['parameters'])
            else:
                sdk=env.core.sdk_observation
                if reflection!='none':
                    sdk=replace(sdk,samples=tuple(replace(sample,value=direction*sample.value,frame_id=canonical_frame)
                        if sample.channel in env.core.channels[:4] else sample for sample in sdk.samples))
                intent=policy.act(sdk)
                if intent is None: raise RuntimeError(policy.fault_reason)
                raw,mode=direction*intent.acceleration_m_s2,policy.mode
                if candidate['actor']=='host_schedule':
                    raw,settled=settled_acceleration(float(x),float(v),theta,float(w),raw,{**DEFAULTS,**candidate['parameters']})
                    raw=max(-25.,min(25.,raw))
                    if settled: mode+=':settled'
                elif candidate['actor']=='host_latch':
                    p={**DEFAULTS,**candidate['parameters']}
                    _,eligible=settled_acceleration(float(x),float(v),theta,float(w),raw,p)
                    settled_latched=policy.mode=='balance' and (settled_latched or eligible)
                    if settled_latched:
                        raw=max(-25.,min(25.,p['settled_position_gain']*x+p['settled_velocity_gain']*v+p['settled_theta_gain']*theta+p['settled_omega_gain']*w))
                        mode+=':settled_latched'
            observed=dict(state=observation['state'].tolist(),age_s=observation['age_s'].tolist(),
                          valid=observation['valid'].tolist(),theta=theta)
            if mode!=previous_mode:
                transitions.append(dict(t_s=env.steps*.01,mode=mode,observed_before_action=observed))
                previous_mode=mode
            observation,_,terminated,truncated,_=env.step([raw/env.action_scale])
            truth=env.core.ground_truth
            if first_five is None and env.dwell>=5.-1e-9: first_five=env.steps*.01
            trace.append(dict(t_s=env.steps*.01,observed_before_action=observed,
                x=truth.x,v=truth.v,theta=truth.theta,omega=truth.omega,raw=raw,mode=mode,
                executed=env.core.diagnostics.executed_acceleration_m_s2,
                strict_balanced=abs(truth.x)<.12 and abs(truth.theta)<.15 and abs(truth.omega)<1,
                rail_braking=bool(env.core.diagnostics.rail_braking)))
            if terminated or truncated: break
        result=env.result(hold_seconds=5.)
        result.update(controller_reflection_sign=direction,first_five_second_hold_s=first_five,transitions=transitions,wall_seconds=time.monotonic()-began)
        for label,rows in [('all',trace),('last5s',trace[-500:])]:
            xs=np.array([r['x'] for r in rows]); raw=np.array([r['raw'] for r in rows])
            result[label]=dict(x_rms_m=float(np.sqrt(np.mean(xs*xs))),max_abs_x_m=float(np.max(np.abs(xs))),
                x_peak_to_peak_m=float(np.ptp(xs)),raw_action_rms=float(np.sqrt(np.mean(raw*raw))),
                raw_action_delta_rms=float(np.sqrt(np.mean(np.diff(raw)**2))) if len(raw)>1 else 0.,
                max_abs_theta_rad=max(abs(r['theta']) for r in rows),
                max_abs_omega_rad_s=max(abs(r['omega']) for r in rows))
        return result,trace
    finally: env.close()


def aggregate(episodes,seconds):
    return dict(episodes=len(episodes),hold_successes=sum(e['hold_success'] for e in episodes),
        ever_five_second_holds=sum(e['first_five_second_hold_s'] is not None for e in episodes),
        faults=sum(e['fault_reason'] is not None for e in episodes),
        min_final_dwell_s=min(e['final_balance_dwell_s'] for e in episodes),
        mean_first_five_second_hold_s=float(np.mean([e['first_five_second_hold_s'] or (seconds+10) for e in episodes])),
        mean_longest_dwell_s=float(np.mean([e['longest_balance_dwell_s'] for e in episodes])),
        mean_score=float(np.mean([e['score'] for e in episodes])),
        max_abs_x_m=max(e['max_abs_x_m'] for e in episodes),
        rail_braking_control_steps=sum(e['rail_braking_control_steps'] for e in episodes))


def objective(summary):
    return 1000*summary['faults']+100*(summary['episodes']-summary['hold_successes'])+summary['mean_first_five_second_hold_s']-summary['mean_score']


def write_json(path,value): path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def snapshot(output,profile):
    files=[ROOT/'pyproject.toml',ROOT/'uv.lock',Path(__file__),*sorted((ROOT/'src').rglob('*.py')),
           *sorted(profile.glob('*.json')),*sorted((ROOT/'src/cartpole_sdk').rglob('*.json')),
           *sorted((ROOT/'src/cartpole_sdk').rglob('*.xml'))]
    manifest={str(p.relative_to(ROOT)):sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()}
    with zipfile.ZipFile(output/'source.zip','x',zipfile.ZIP_DEFLATED) as archive:
        for name in manifest: archive.write(ROOT/name,name)
    return manifest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--profile',type=Path,default=ROOT/'training/profiles/rl-encoder-20261017')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--seconds',type=float,choices=(10.,15.,20.,25.,60.),default=15.)
    p.add_argument('--seeds',type=int,nargs='+',default=[52000])
    p.add_argument('--starts',nargs='+',choices=('hanging','upright'),default=['hanging','upright'])
    p.add_argument('--candidates',type=Path)
    p.add_argument('--purpose',choices=('development','expanded_development','demonstrations','frozen_evaluation'),default='development')
    args=p.parse_args()
    allowed=(range(52000,52006) if args.purpose=='development' else range(21000,21008) if args.purpose=='expanded_development' else range(55000,55008) if args.purpose=='frozen_evaluation' else range(21000,21016))
    if any(s not in allowed for s in args.seeds) or len(set(args.seeds))!=len(args.seeds):
        p.error('purpose requires distinct development52000..52005,expanded development21000..21007,or demonstration21000..21015 seeds')
    if args.purpose=='frozen_evaluation' and (args.seeds!=list(range(55000,55008)) or set(args.starts)!={'hanging','upright'} or args.seconds!=60.):
        p.error('frozen evaluation requires all55000..55007,both starts,60seconds')
    if args.purpose=='demonstrations' and (args.seeds!=list(range(21000,21016)) or set(args.starts)!={'hanging','upright'} or args.seconds!=25.):
        p.error('demonstrations require all21000..21015, both starts,25seconds')
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
    if args.purpose in ('demonstrations','frozen_evaluation') and len(candidates)!=1:
        p.error('freeze exactly one teacher before demonstrations')
    names=[c['name'] for c in candidates]
    if len(set(names))!=len(names) or not names or any(not n.replace('_','').isalnum() for n in names):
        raise ValueError('unique safe names required')
    for c in candidates:
        if c.get('reflection','none') not in ('none','initial_x','negative'): raise ValueError('unsupported reflection')
        if c.get('reflection','none')!='none' and c['actor']=='memoryless': raise ValueError('reflection supported only for stateful host candidates')
        if c['actor'] not in ('memoryless','host','host_schedule','host_latch'): raise ValueError('unsupported actor')
        if c['actor']=='memoryless' and set(c['parameters'])-set(DEFAULTS): raise ValueError('unknown parameter')
        if not all(math.isfinite(v) for v in c['parameters'].values()): raise ValueError('finite parameters required')
    args.output.mkdir(parents=True,exist_ok=False)
    pins=diagnostic_provenance(); manifest=snapshot(args.output,args.profile.resolve())
    seed_role=('fresh55000..55007 frozen candidate evaluation; never used for tuning' if args.purpose=='frozen_evaluation' else 'adaptively inspected development seeds only; no held-out evaluation' if args.purpose!='demonstrations' else 'imitation train21000..21011,validation21012..21015; all starts for a seed share split')
    recipe=dict(schema='cartpole-local-swing-teacher-search-v1',status='DEVELOPMENT_ONLY',hardware_accepted=False,
        deployable=False,simulation_only=True,randomization=None,seeds=args.seeds,starts=args.starts,
        purpose=args.purpose,seed_role=seed_role,seconds=args.seconds,
        threads=1,experiment=experiment,experiment_sha256=experiment_identity(experiment),provenance=pins,
        source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        source_manifest=manifest,source_zip_sha256=sha256((args.output/'source.zip').read_bytes()).hexdigest(),
        candidates=candidates,memoryless_defaults=DEFAULTS,
        actor_input='observed x,v,sin(theta),cos(theta),omega only; host path validated SDK observations; truth metrics after action',
        ranking='faults then final 5-second hold failures then time-to-first-5-second-hold minus score',
        command=sys.argv)
    write_json(args.output/'recipe.json',recipe)
    report=dict(recipe_sha256=sha256((args.output/'recipe.json').read_bytes()).hexdigest(),completed=False,candidates=[])
    began=time.monotonic(); demonstration_rows=[]
    for candidate in candidates:
        episodes=[]; folder=args.output/candidate['name']; folder.mkdir()
        for seed in args.seeds:
            for start in args.starts:
                episode,trace=run_episode(experiment,candidate,seed,start)
                path=folder/f'{start}-{seed}.jsonl.gz'
                with gzip.open(path,'wt') as stream:
                    for row in trace: stream.write(json.dumps(row,allow_nan=False)+'\n')
                episode['trajectory_path']=str(path.relative_to(args.output))
                episode['trajectory_sha256']=sha256(path.read_bytes()).hexdigest()
                episodes.append(episode)
                if args.purpose=='demonstrations':
                    demonstration_rows.extend((seed,row) for row in trace)
                print(json.dumps(dict(name=candidate['name'],seed=seed,start=start,hold=episode['hold_success'],
                    first5=episode['first_five_second_hold_s'],dwell=episode['longest_balance_dwell_s'],
                    score=episode['score'],fault=episode['fault_reason'])),flush=True)
        summary=aggregate(episodes,args.seconds)
        report['candidates'].append(dict(**candidate,episodes=episodes,summary=summary,objective=objective(summary)))
        report['wall_seconds']=time.monotonic()-began
        write_json(args.output/'report.json',report)
    if diagnostic_provenance()!=pins: raise RuntimeError('source or dependency changed during search')
    report['ranking']=[r['name'] for r in sorted(report['candidates'],key=lambda r:r['objective'])]
    report['completed']=True; write_json(args.output/'report.json',report)
    best=min(report['candidates'],key=lambda r:r['objective'])
    write_json(args.output/'teacher.json',dict(schema='cartpole-exploratory-swing-teacher-v1',status='DEVELOPMENT_ONLY',
        deployable=False,hardware_accepted=False,simulation_only=True,candidate=candidates[names.index(best['name'])],
        defaults=DEFAULTS,summary=best['summary'],hidden_state_required=best['actor']!='memoryless',
        report_sha256=sha256((args.output/'report.json').read_bytes()).hexdigest(),recipe_sha256=report['recipe_sha256'],
        script_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))
    if args.purpose=='demonstrations':
        arrays={key:np.asarray([row['observed_before_action'][key] for _,row in demonstration_rows],dtype=np.int8 if key=='valid' else np.float64)
                for key in ('state','valid','age_s')}
        arrays['raw_action']=np.asarray([row['raw'] for _,row in demonstration_rows],dtype=np.float64)
        arrays['episode']=np.asarray([seed for seed,_ in demonstration_rows],dtype=np.int64)
        path=args.output/'demonstrations.npz'
        with path.open('xb') as stream: np.savez_compressed(stream,**arrays)
        metadata=dict(schema='cartpole-swing-demonstrations-v1',status='DEVELOPMENT_ONLY',
            hardware_accepted=False,deployable=False,simulation_only=True,
            candidate=candidates[0],hidden_state_required=candidates[0]['actor']!='memoryless',
            hidden_state_description='host swing/balance hysteresis, initial timed kick, optional constant initial-x coordinate reflection sign, plus settled latch if actor host_latch',
            training_pose_seeds=list(range(21000,21012)),validation_pose_seeds=list(range(21012,21016)),
            both_starts_share_pose_split=True,all_successes_and_failures_retained=True,
            demonstration_rows=len(demonstration_rows),npz_sha256=sha256(path.read_bytes()).hexdigest(),
            teacher_sha256=sha256((args.output/'teacher.json').read_bytes()).hexdigest(),
            recipe_sha256=report['recipe_sha256'],report_sha256=sha256((args.output/'report.json').read_bytes()).hexdigest(),
            source_zip_sha256=recipe['source_zip_sha256'],experiment_sha256=recipe['experiment_sha256'],
            script_sha256=manifest[str(Path(__file__).relative_to(ROOT))],
            trajectories=[dict(seed=e['seed'],start=e['start'],path=e['trajectory_path'],sha256=e['trajectory_sha256'],
                hold_success=e['hold_success'],fault_reason=e['fault_reason'],steps=e['steps']) for e in best['episodes']],
            summary=best['summary'])
        with (args.output/'demonstrations-metadata.json').open('x') as stream:
            stream.write(json.dumps(metadata,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(completed=True,ranking=report['ranking'],wall_seconds=report['wall_seconds'])),flush=True)

if __name__=='__main__': main()
