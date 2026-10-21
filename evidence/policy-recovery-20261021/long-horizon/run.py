#!/usr/bin/env python3
"""Frozen BAL feedback: bounded fresh-start long-horizon diagnostic, no training."""
import argparse
from copy import deepcopy
from dataclasses import asdict, replace
from hashlib import sha256
import json
import math
from pathlib import Path
import zipfile
import numpy as np
from cartpole_sdk.control.parameters import ControllerParameters, gains
from cartpole_sdk.learning.model_experiment import validate_experiment
from cartpole_sdk.policies.neural import load_neural_policy
from cartpole_sdk.policies.numeric_backend import NumpyActorBackend
from cartpole_sdk.policies.rig_observation import rig_channels, encode_rig_observation, select_rig_observation
from cartpole_sdk.sim.rig_gym_env import RigCartpoleEnv

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
PRIOR=HERE.parent/'teacher-transfer'
ACTOR=ROOT/'training/candidates/balance-recovery-20261021/actor.json'
CHECKPOINT=PRIOR/'bal-filtered-supervised-seed47.zip'
SEEDS=(97410,97411,97412,97413)
BIASES=(0.,-1.,1.)
ARMS=('analytic_BAL_filtered','MLP_BAL_filtered')

def digest(path): return sha256(path.read_bytes()).hexdigest()
def write(path,value):
    with path.open('x') as stream:
        json.dump(value,stream,indent=2,sort_keys=True,allow_nan=False)
        stream.write('\n')
def manifest():
    paths=sorted(p for parent in (ROOT/'src/cartpole_sdk',ROOT/'src/cartpole_vision')
                 for p in parent.rglob('*') if p.is_file() and p.suffix in ('.py','.json'))
    return {str(p.relative_to(ROOT)):digest(p) for p in paths}
def teacher(state,k):
    x,v,s,c,w,_,_=state
    return float(np.clip(k['position_gain']*x+k['velocity_gain']*v+
        k['theta_gain']*math.atan2(s,c)+k['omega_gain']*w,-25.,25.))
def declare():
    prior=json.loads((PRIOR/'protocol.json').read_text())
    experiment=deepcopy(prior['experiment']); experiment['simulation_config']['max_steps']=6000
    validate_experiment(experiment)
    g=gains(ControllerParameters(**experiment['executor_parameters']),upright=True)
    k=dict(position_gain=-g.k3,velocity_gain=-g.k4,theta_gain=-g.k1,omega_gain=-g.k2)
    assert k==prior['teacher']['gains']
    starts=[]
    for seed in SEEDS:
        q=np.random.default_rng(np.random.SeedSequence([seed,814])).uniform(
            [-.005,-.005,-math.radians(1.),-.02],[.005,.005,math.radians(1.),.02])
        starts.append(dict(seed=seed,initial_state=q.tolist()))
    source=manifest()
    # Physical, sensing, governor and observer implementation must remain the
    # exact same versions as in the frozen supervised-transfer experiment.
    retained=('sim/rig_gym_env.py','sim/backend.py','sim/executor.py','sim/model.py',
              'sim/config.py','control/motion.py','control/parameters.py','control/reference.py')
    for name in retained:
        assert source['src/cartpole_sdk/'+name]==prior['source']['code_sha256'][name],name
    with zipfile.ZipFile(HERE/'source.zip','x',zipfile.ZIP_DEFLATED) as archive:
        for name in source: archive.write(ROOT/name,name)
        archive.write(Path(__file__),'long-horizon/run.py')
    policy=load_neural_policy(ACTOR,channels=rig_channels(angle_source='filtered'))
    protocol=dict(status='DEVELOPMENT_ONLY',hardware_accepted=False,deployable=False,
        purpose='Longer nonlinear simulation of unchanged actual filtered BAL feedback and its frozen supervised learned approximation. No PPO, fit, selection, export or hardware actions.',
        experiment=experiment,teacher_gains=k,arms=list(ARMS),starts=starts,bias_degrees=list(BIASES),
        seconds=60.,report_horizons_s=[25.,60.],trajectories=24,workers=1,
        initial_state_order=['x_m','v_m_s','theta_rad','omega_rad_s'],
        initial_distribution=dict(generator='NumPy default_rng(SeedSequence([seed,814])) uniform',
            bounds=[[-.005,.005],[-.005,.005],[-math.radians(1.),math.radians(1.)],[-.02,.02]]),
        ordering='All zero-bias matched pairs first, then -1 degree, then +1 degree; each seed analytic then MLP.',
        horizon_semantics='25s is the exact prefix of the same 60s run; no intervening reset or selection. Horizon affects only truncation.',
        bias_semantics='Replace only upstream encoder_bias_rad, before quantization and filtering; true plant initial angle is unchanged.',
        startup_semantics='Existing RigCartpoleEnv reset including causal sensor/plant warmup; no added settling. Literal initial state, reset ground truth and observation saved.',
        success_definition='Complete horizon with no fault and final >=5 seconds continuously abs(true x)<.12m, abs(true theta)<.15rad and abs(true omega)<1rad/s.',
        feedback_scope='Exact BAL raw demand law and emitted MLP numeric actor, each clipped to25m/s2 and passed through unchanged model executor/governor. Does not emulate native1kHz scheduling, native AUTO state machine, or hardware BalanceOnlyPolicy stopping guards.',
        metrics='Final/max/total true-state balance dwell; first hold exit; centering mean/RMS/std and max excursion; angle/rate and detrended FFT oscillation; raw command variation; rail braking and model faults. Tail window is final5s at each horizon.',
        source_sha256=source,source_zip_sha256=digest(HERE/'source.zip'),script_sha256=digest(Path(__file__)),
        unchanged_physical_source_files=list(retained),
        bindings={str(p.relative_to(ROOT)):digest(p) for p in (ACTOR,CHECKPOINT,PRIOR/'protocol.json',PRIOR/'fit-report.json')},
        actor_content_sha256=policy.actor['content_sha256'],
        limitations=['Four fresh starts are a small development sample, not a reliability estimate or hardware qualification.',
            'Unchanged passive-fit plant, ideal acceleration servo, delays and near-upright friction remain imperfect/unidentified.',
            'A constant +/-1 degree offset is a bounded sensitivity condition; it does not establish a calibration-error distribution or sensor-fault cause.',
            'Recent corrected-reference native BAL hardware held10s; prior bad-reference failures do not establish a persistent physical sensor fault.',
            'Same fixed100Hz contract, bandwidth10, jerk150 and rail as original candidate; no hardware writes or retuning.',
            'This is supervised initialization, not PPO improvement. All failures are retained.'])
    write(HERE/'protocol.json',protocol)
    print(json.dumps(dict(declared=True,protocol_sha256=digest(HERE/'protocol.json'),starts=starts,actor_content_sha256=protocol['actor_content_sha256'])),flush=True)

def spectrum(values):
    a=np.asarray(values,float)
    if len(a)<100: return None
    a=a-np.mean(a); power=np.abs(np.fft.rfft(a*np.hanning(len(a))))**2
    freq=np.fft.rfftfreq(len(a),.01); select=(freq>=.1)&(freq<=20.)
    if not np.any(select) or float(np.sum(power[select]))<=1e-24: return None
    indices=np.flatnonzero(select); i=indices[np.argmax(power[select])]
    return dict(dominant_hz=float(freq[i]),dominant_bin_power_fraction=float(power[i]/np.sum(power[select])))

def summarize(rows,seconds,fault):
    n=round(seconds*100); prefix=rows[:n]; complete=len(prefix)==n
    if not prefix: return dict(horizon_s=seconds,full_horizon_complete=False,hold_success=False,steps=0,fault=fault)
    x=np.array([r['truth']['x'] for r in prefix]);theta=np.array([r['truth']['theta'] for r in prefix])
    omega=np.array([r['truth']['omega'] for r in prefix]);command=np.array([r['raw_command_m_s2'] for r in prefix])
    balanced=np.array([r['balanced'] for r in prefix]); dwell=maxdwell=0
    for value in balanced:
        dwell=dwell+1 if value else 0;maxdwell=max(maxdwell,dwell)
    # A fault after25s does not invalidate a completed25s prefix.
    horizon_fault=next((r['fault'] for r in prefix if r['fault'] is not None),None)
    if not complete and horizon_fault is None:horizon_fault=fault
    tail=slice(max(0,len(prefix)-500),len(prefix))
    rms=lambda a:float(np.sqrt(np.mean(a*a)))
    first=lambda predicate:next((r['t'] for r in prefix if predicate(r)),None)
    differences=np.diff(command)
    return dict(horizon_s=seconds,steps=len(prefix),elapsed_s=prefix[-1]['t'],full_horizon_complete=complete,
        fault=horizon_fault,hold_success=bool(complete and horizon_fault is None and dwell>=500),
        final_balance_dwell_s=dwell/100.,max_balance_dwell_s=maxdwell/100.,total_balanced_s=float(sum(balanced))/100.,
        balanced_fraction=float(np.mean(balanced)),first_hold_exit_s=first(lambda r:not r['balanced']),
        max_abs_x_m=float(np.max(np.abs(x))),min_x_m=float(np.min(x)),max_x_m=float(np.max(x)),
        final_x_m=float(x[-1]),tail_x_mean_m=float(np.mean(x[tail])),tail_x_rms_m=rms(x[tail]),tail_x_std_m=float(np.std(x[tail])),
        max_abs_theta_deg=math.degrees(float(np.max(np.abs(theta)))),tail_theta_rms_deg=math.degrees(rms(theta[tail])),
        tail_theta_std_deg=math.degrees(float(np.std(theta[tail]))),max_abs_omega_rad_s=float(np.max(np.abs(omega))),
        first_angle_over5deg_s=first(lambda r:abs(r['truth']['theta'])>math.radians(5.)),
        first_rail_braking_s=first(lambda r:r['rail_braking']),rail_braking_steps=sum(r['rail_braking'] for r in prefix),
        max_abs_command_m_s2=float(np.max(np.abs(command))),tail_command_rms_m_s2=rms(command[tail]),
        command_total_variation_per_s=float(np.sum(np.abs(differences))/prefix[-1]['t']),
        command_delta_p95_m_s2=float(np.quantile(np.abs(differences),.95)) if len(differences) else 0.,
        tail_theta_spectrum=spectrum(theta[tail]),tail_command_spectrum=spectrum(command[tail]))

def episode(protocol,backend,arm,start,bias):
    config,parameters,observations,_=validate_experiment(protocol['experiment'])
    observations=replace(observations,encoder_bias_rad=math.radians(bias))
    env=RigCartpoleEnv(config,parameters=parameters,observation_config=observations,ttl_ms=20)
    seed=start['seed'];path=HERE/'traces'/f'{arm}-seed{seed}-bias{bias:+.1f}.jsonl'
    try:
        env.reset(seed=seed,options={'state':start['initial_state']})
        origin=env.ground_truth.time_ns;reset_truth=asdict(env.ground_truth)
        initial_observation=encode_rig_observation(env.sdk_observation,env.channels)
        rows=[];error=None
        with path.open('x') as stream:
            while not(env.terminated or env.truncated):
                try:
                    select_rig_observation(env.sdk_observation,env.channels,contract=env.observation_contract)
                    encoded=encode_rig_observation(env.sdk_observation,env.channels)
                    expected=teacher(encoded['state'],protocol['teacher_gains'])
                    raw=expected if arm=='analytic_BAL_filtered' else backend.predict_encoded(encoded)
                    decision_ns=env.sdk_observation.available_ns
                    env.step([raw])
                except Exception as exc:
                    error=f'{type(exc).__name__}: {exc}';break
                truth=asdict(env.ground_truth)
                row=dict(t=(truth['time_ns']-origin)/1e9,decision_available_ns=decision_ns,encoded_observation=encoded,
                    truth=truth,raw_command_m_s2=raw,analytic_BAL_on_same_observation_m_s2=expected,
                    executed_acceleration_m_s2=env.diagnostics.executed_acceleration_m_s2,
                    rail_braking=bool(env.diagnostics.rail_braking),fault=env.fault_reason,
                    balanced=abs(truth['x'])<.12 and abs(truth['theta'])<.15 and abs(truth['omega'])<1.)
                rows.append(row);stream.write(json.dumps(row,sort_keys=True,allow_nan=False)+'\n')
        fault=error or env.fault_reason
        result=dict(arm=arm,seed=seed,bias_degrees=bias,literal_initial_state=start['initial_state'],reset_truth=reset_truth,
            reset_warmup_ns=origin,initial_encoded_observation=initial_observation,steps=len(rows),fault=fault,
            horizons=[summarize(rows,seconds,fault) for seconds in protocol['report_horizons_s']],
            trace_path=str(path.relative_to(HERE)),trace_sha256=digest(path))
        write(path.with_suffix('.summary.json'),result)
        return result
    finally:env.close()

def run():
    protocol=json.loads((HERE/'protocol.json').read_text())
    assert digest(Path(__file__))==protocol['script_sha256']
    assert manifest()==protocol['source_sha256']
    for name,expected in protocol['bindings'].items():assert digest(ROOT/name)==expected,name
    policy=load_neural_policy(ACTOR,channels=rig_channels(angle_source='filtered'));backend=NumpyActorBackend(policy.actor)
    assert policy.actor['content_sha256']==protocol['actor_content_sha256']
    (HERE/'traces').mkdir(exist_ok=False)
    rows=[]
    for bias in protocol['bias_degrees']:
        for start in protocol['starts']:
            for arm in protocol['arms']:
                row=episode(protocol,backend,arm,start,bias);rows.append(row)
                print(json.dumps(dict(arm=arm,seed=start['seed'],bias=bias,fault=row['fault'],
                    horizons=[{k:h[k] for k in ('horizon_s','hold_success','final_balance_dwell_s','max_abs_x_m','tail_theta_rms_deg','rail_braking_steps')} for h in row['horizons']])),flush=True)
    summaries=[]
    for seconds in protocol['report_horizons_s']:
        for bias in protocol['bias_degrees']:
            for arm in protocol['arms']:
                selected=[h for r in rows if r['arm']==arm and r['bias_degrees']==bias for h in r['horizons'] if h['horizon_s']==seconds]
                summaries.append(dict(horizon_s=seconds,bias_degrees=bias,arm=arm,episodes=len(selected),
                    holds=sum(h['hold_success'] for h in selected),faults=sum(h['fault'] is not None for h in selected),
                    all_horizon_balanced=sum(h['balanced_fraction']==1. for h in selected),
                    worst_max_abs_x_m=max(h['max_abs_x_m'] for h in selected),
                    worst_tail_theta_rms_deg=max(h['tail_theta_rms_deg'] for h in selected),
                    min_final_dwell_s=min(h['final_balance_dwell_s'] for h in selected),
                    episodes_with_rail_braking=sum(h['rail_braking_steps']>0 for h in selected)))
    assert manifest()==protocol['source_sha256']
    for name,expected in protocol['bindings'].items():assert digest(ROOT/name)==expected,name
    report=dict(status='DEVELOPMENT_ONLY',hardware_accepted=False,deployable=False,simulation_only=True,
        protocol_sha256=digest(HERE/'protocol.json'),source_zip_sha256=protocol['source_zip_sha256'],
        actor_content_sha256=protocol['actor_content_sha256'],all_bound_inputs_unchanged=True,
        summaries=summaries,episodes=rows,limitations=protocol['limitations'])
    write(HERE/'report.json',report)
    print(json.dumps(dict(complete=True,report_sha256=digest(HERE/'report.json'),summaries=summaries)),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=('declare','run'))
    args=parser.parse_args();declare() if args.mode=='declare' else run()
