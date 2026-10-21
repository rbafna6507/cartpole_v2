#!/usr/bin/env python3
"""Predeclared analytic-teacher screen; no neural fitting, export, or hardware."""
import argparse
from dataclasses import asdict, replace
from hashlib import sha256
import json
import math
from pathlib import Path

import numpy as np
import torch

from cartpole_sdk.contracts import ValidationError
from cartpole_sdk.learning.balance_experiment import source_identity
from cartpole_sdk.learning.model_experiment import validate_experiment
from cartpole_sdk.learning.rollout import initial_state
from cartpole_sdk.policies.rig_observation import encode_rig_observation, select_rig_observation
from cartpole_sdk.sim.rig_gym_env import RigCartpoleEnv

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RUN = ROOT / 'runs/policy-confidence-20261021/balance/teacher-seed47'
GAIN_NAMES = ('position_gain', 'velocity_gain', 'theta_gain', 'omega_gain')
CANDIDATES = [
    ('original-control', (1., 2., 40., 2.)),
    ('center04-v04-t40-o3', (4., 4., 40., 3.)),
    ('center04-v04-t60-o3', (4., 4., 60., 3.)),
    ('center04-v05-t60-o3', (4., 5., 60., 3.)),
    ('center04-v06-t60-o3', (4., 6., 60., 3.)),
    ('center06-v05-t60-o3', (6., 5., 60., 3.)),
    ('center06-v06-t60-o3', (6., 6., 60., 3.)),
    ('center06-v07-t60-o3', (6., 7., 60., 3.)),
    ('center08-v07-t60-o4', (8., 7., 60., 4.)),
    ('center12-v09-t60-o4', (12., 9., 60., 4.)),
    ('center20-v12-t60-o5', (20., 12., 60., 5.)),
]
BIASES = (0., -.25, .25, -.5, .5)


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def write_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def linearization(config, parameters, gains):
    length = config.effective_length_m
    inertia = .75 * config.pole_mass_kg * length ** 2
    friction_slope = config.hinge_coulomb_friction_nm / config.hinge_friction_velocity_scale_rad_s
    damping = (config.hinge_damping + friction_slope) / inertia
    w = 2 * math.pi * parameters.bw
    kx, kv, kt, ko = (gains[name] for name in GAIN_NAMES)
    matrix = np.array([
        [0, 1, 0, 0, 0, 0],
        [kx, kv, kt, 0, 0, ko],
        [0, 0, 0, 1, 0, 0],
        [-kx / length, -kv / length, (9.81 - kt) / length, -damping, 0, -ko / length],
        [0, 0, 2 * w, 0, -2 * w, 1],
        [0, 0, w ** 2, 0, -w ** 2, 0],
    ], dtype=float)
    eigenvalues = np.linalg.eigvals(matrix)
    return dict(gains=gains, state_order=['x','v','theta','omega','angle_hat','rate_hat'], matrix=matrix.tolist(),
        eigenvalues=[dict(real=float(value.real), imag=float(value.imag)) for value in eigenvalues],
        maximum_real_eigenvalue_per_s=float(max(eigenvalues.real)),
        locally_stable=bool(max(eigenvalues.real) < -1e-6),
        effective_length_m=length, uniform_rod_length_m=1.5 * length,
        pole_mass_kg=config.pole_mass_kg, pivot_inertia_kg_m2=inertia,
        hinge_damping_nm_per_rad_s=config.hinge_damping,
        hinge_coulomb_friction_nm=config.hinge_coulomb_friction_nm,
        hinge_friction_velocity_scale_rad_s=config.hinge_friction_velocity_scale_rad_s,
        coulomb_tanh_slope_nm_per_rad_s=friction_slope,
        combined_angular_damping_per_s=damping, observer_bandwidth_hz=parameters.bw,
        observer_w_per_s=w)


def declare():
    if (HERE / 'protocol.json').exists():
        raise FileExistsError('protocol already declared')
    training = json.loads((RUN / 'recipe.json').read_text())
    report = json.loads((RUN / 'report.json').read_text())
    assert digest(RUN / 'recipe.json') == report['recipe_sha256']
    assert digest(RUN / 'source.zip') == report['source_zip_sha256']
    assert source_identity() == training['provenance']
    config, parameters, observations, _ = validate_experiment(training['experiment'])
    entries = [dict(name=name, control=name == 'original-control', gains=dict(zip(GAIN_NAMES, values))) for name, values in CANDIDATES]
    local = {entry['name']: linearization(config, parameters, entry['gains']) for entry in entries}
    protocol = dict(schema='cartpole-analytic-centering-teacher-screen-v1', status='DEVELOPMENT_ONLY',
        simulation_only=True, hardware_accepted=False, deployable=False,
        branch='New analytic teacher / possible future supervised initialization; distinct from PPO improvement and original joint-candidate selection.',
        candidates=entries, control='original-control', simulation_source=source_identity(),
        training_recipe_path=str(RUN / 'recipe.json'), training_recipe_sha256=digest(RUN / 'recipe.json'),
        source_archive_path=str(RUN / 'source.zip'), source_archive_sha256=digest(RUN / 'source.zip'),
        script_sha256=digest(Path(__file__)), experiment=training['experiment'],
        development=dict(seeds=[94000,94007], seconds=10., starts=['upright'], encoder_bias_degrees=list(BIASES)),
        confirmation=dict(seeds=[97000,97001,97002,97003], seconds=30., starts=['upright'], encoder_bias_degrees=list(BIASES),
            rule='Run only a single frozen winning alternative after development; do not tune or select a runner-up using confirmation.'),
        linear_gate=dict(criterion='All real parts of continuous local closed-loop eigenvalues < -1e-6 per second.',
            state_order=['x','v','theta','omega','angle_hat','rate_hat'],
            plant_equations=['xdot=v', 'vdot=a', 'thetadot=omega',
                'omegadot=(9.81*theta-a)/L_eff - ((hinge_damping+coulomb/tanh_width)/I_pivot)*omega',
                'I_pivot=mass*(1.5*L_eff)^2/3=0.75*mass*L_eff^2'],
            controller_equation='a=kx*x+kv*v+ktheta*theta+komega*rate_hat',
            observer_equations=['w=2*pi*bw', 'angle_hat_dot=rate_hat+2*w*(theta-angle_hat)', 'rate_hat_dot=w^2*(theta-angle_hat)'],
            actual_observer_tick='angle_hat_next=wrap(angle_hat+(rate_hat+2*w*error)*.001), rate_hat_next=rate_hat+w*w*error*.001',
            limitations='Continuous unquantized local necessary screen with compensated acceleration and actual friction slope; omits sample/transport delay, quantization, clipping, jerk limits and rail guards. Nonlinear simulator retains them all.',
            friction_scope='Exact current fitted tanh Coulomb and viscous terms; fit validated on free swings, not tiny upright corrections. No physical coefficients changed.'),
        nonlinear_law='At100Hz: clip(kx*observed_x+kv*observed_v+ktheta*atan2(observed_sin,observed_cos)+komega*observed_rate,-25,25). No truth in controller.',
        bias_intervention='Upstream encoder_bias_rad before unchanged sensor noise, quantization and observer.',
        matching='Same seeds/initial-state function and random draw sequence for each candidate/bias; unchanged plant/governor/parameters/TTL20ms.',
        eligibility='Alternative must pass local gate and all10 development final holds with full10s and no simulator/policy fault. Original law is a comparator, not a replacement candidate.',
        hold_definition='Whole final5s true abs(theta)<.15rad, abs(omega)<1rad/s, abs(x)<.12m; complete episode without fault.',
        ranking=['minimum worst max_abs_x_m across all10 episodes', 'minimum worst raw-command adjacent-difference RMS across all10 episodes', 'candidate name ascending tie-break'],
        if_no_winner='Stop after development; do not access confirmation poses, fit, or export.',
        if_winner='Write frozen-winner receipt with development/protocol hashes before any confirmation. Require all20 confirmation holds/no faults before reporting analytic teacher as passed.',
        workers=1, torch_threads=1, local_linearization=local,
        limitations=['Small reused development sample; selection only within the declared finite set.',
                    'Fresh confirmation tests this analytic teacher, not an untrained neural approximation or hardware.',
                    'No hardware qualification, runtime source edits, neural fitting or actor export in this branch.'])
    write_new(HERE / 'protocol.json', protocol)
    write_new(HERE / 'linearization.json', dict(protocol_sha256=digest(HERE / 'protocol.json'), candidates=local))
    print(json.dumps(dict(protocol_sha256=digest(HERE / 'protocol.json'),
        local_screens={name: dict(stable=row['locally_stable'], max_real_per_s=row['maximum_real_eigenvalue_per_s']) for name,row in local.items()}), indent=2))


def episode(experiment, gains, candidate, seed, bias, seconds, stage):
    config, parameters, observations, _ = validate_experiment(experiment)
    config = replace(config, max_steps=round(seconds * 100))
    observations = replace(observations, encoder_bias_rad=math.radians(bias))
    env = RigCartpoleEnv(config, parameters=parameters, observation_config=observations, ttl_ms=experiment['ttl_ms'])
    path = HERE / stage / candidate / f'bias{bias:+.2f}-seed{seed}.jsonl'
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        encoded, _ = env.reset(seed=seed, options=dict(state=initial_state(seed, 'upright')))
        initial = asdict(env.ground_truth)
        reset_ns = env.ground_truth.time_ns
        dwell = longest = 0.
        first_exit = None
        max_x = abs(initial['x'])
        states, commands, executed, balanced_history = [], [], [], []
        fault = None
        with path.open('x') as stream:
            while not (env.terminated or env.truncated):
                try:
                    select_rig_observation(env.sdk_observation, env.channels, contract=env.observation_contract)
                except ValidationError as error:
                    fault = str(error)
                    break
                obs = encode_rig_observation(env.sdk_observation, env.channels)
                assert all(np.array_equal(encoded[key], obs[key]) for key in obs)
                x, v, sin_theta, cos_theta, omega, _, _ = obs['state']
                unclipped = (gains['position_gain']*x + gains['velocity_gain']*v
                    + gains['theta_gain']*math.atan2(sin_theta,cos_theta) + gains['omega_gain']*omega)
                raw = float(np.clip(unclipped, -25., 25.))
                before = env.ground_truth.time_ns
                encoded, _, _, _, info = env.step([raw])
                truth = env.ground_truth
                state = asdict(truth)
                elapsed = (truth.time_ns-reset_ns)/1e9
                balanced = abs(truth.theta)<.15 and abs(truth.omega)<1 and abs(truth.x)<.12
                dwell = dwell+(truth.time_ns-before)/1e9 if balanced else 0.
                longest = max(longest,dwell)
                if not balanced and first_exit is None: first_exit=elapsed
                max_x = max(max_x,abs(truth.x))
                states.append(state); commands.append(raw); executed.append(env.diagnostics.executed_acceleration_m_s2); balanced_history.append(balanced)
                stream.write(json.dumps(dict(t=elapsed, observed=obs, truth=state,
                    raw_unclipped_m_s2=unclipped, raw_command_m_s2=raw,
                    actual_executor_raw_m_s2=env.diagnostics.raw_acceleration_m_s2,
                    executed_acceleration_m_s2=executed[-1], balanced=balanced,
                    fault_reason=env.fault_reason), sort_keys=True, allow_nan=False)+'\n')
        complete = fault is None and env.fault_reason is None and len(states)==config.max_steps
        tail = states[-500:] if complete else []
        rms = lambda values: float(np.sqrt(np.mean(np.square(values)))) if len(values) else None
        return dict(candidate=candidate, gains=gains, seed=seed, encoder_bias_degrees=bias, stage=stage,
            seconds=seconds, initial_state=initial, final_state=asdict(env.ground_truth), steps=len(states),
            full_horizon_complete=complete, hold_success=bool(complete and dwell>=5.-1e-9),
            final_balance_dwell_s=dwell, longest_balance_dwell_s=longest,
            first_exit_balance_s=first_exit, max_abs_x_m=max_x, whole_episode_centering_margin_m=.12-max_x,
            final_window_x_rms_m=rms([s['x'] for s in tail]),
            final_window_x_mean_m=float(np.mean([s['x'] for s in tail])) if tail else None,
            final_window_centering_margin_m=.12-max(abs(s['x']) for s in tail) if tail else None,
            balanced_fraction=sum(balanced_history)/config.max_steps,
            raw_command_rms_m_s2=rms(commands), raw_command_delta_rms_m_s2=rms(np.diff(commands)),
            executed_acceleration_delta_rms_m_s2=rms(np.diff(executed)),
            raw_command_min_m_s2=min(commands) if commands else None,
            raw_command_max_m_s2=max(commands) if commands else None,
            command_clip_count=sum(abs(value)>=25.-1e-9 for value in commands),
            policy_fault_reason=fault, simulator_fault_reason=env.fault_reason,
            trace_path=str(path.relative_to(HERE)), trace_sha256=digest(path))
    finally:
        env.close()


def summarize(name, rows):
    return dict(candidate=name, episodes=len(rows), holds=sum(row['hold_success'] for row in rows),
        faults=sum(row['policy_fault_reason'] is not None or row['simulator_fault_reason'] is not None for row in rows),
        worst_max_abs_x_m=max(row['max_abs_x_m'] for row in rows),
        worst_command_delta_rms_m_s2=max(row['raw_command_delta_rms_m_s2'] for row in rows),
        all_pass=all(row['hold_success'] for row in rows),
        by_bias=[dict(encoder_bias_degrees=bias, holds=sum(row['hold_success'] for row in rows if row['encoder_bias_degrees']==bias)) for bias in BIASES])


def run():
    protocol = json.loads((HERE / 'protocol.json').read_text())
    assert protocol['script_sha256']==digest(Path(__file__))
    assert source_identity()==protocol['simulation_source']
    if (HERE / 'development-report.json').exists(): raise FileExistsError('development report already exists')
    torch.set_num_threads(1)
    all_rows, summaries, rejected = [], [], []
    for candidate in protocol['candidates']:
        name = candidate['name']
        if not protocol['local_linearization'][name]['locally_stable']:
            rejected.append(dict(candidate=name, reason='local linear stability gate',
                maximum_real_eigenvalue_per_s=protocol['local_linearization'][name]['maximum_real_eigenvalue_per_s']))
            continue
        rows = []
        for bias in protocol['development']['encoder_bias_degrees']:
            for seed in protocol['development']['seeds']:
                rows.append(episode(protocol['experiment'], candidate['gains'], name, seed, bias, 10., 'development'))
        assert source_identity()==protocol['simulation_source']
        summary = summarize(name, rows)
        summaries.append(summary); all_rows.extend(rows)
        write_new(HERE / 'development' / name / 'report.json', dict(summary=summary, episodes=rows))
        print(json.dumps(summary), flush=True)
    eligible = [row for row in summaries if row['candidate']!=protocol['control'] and row['episodes']==10 and row['holds']==10 and row['faults']==0]
    eligible.sort(key=lambda row:(row['worst_max_abs_x_m'],row['worst_command_delta_rms_m_s2'],row['candidate']))
    report = dict(status='DEVELOPMENT_ONLY', completed=True, hardware_accepted=False, deployable=False,
        protocol_sha256=digest(HERE / 'protocol.json'), summaries=summaries, rejected_before_simulation=rejected,
        eligible_ranking=eligible, episodes=all_rows, confirmation_accessed=False)
    write_new(HERE / 'development-report.json', report)
    if not eligible:
        write_new(HERE / 'final-report.json', dict(status='DEVELOPMENT_ONLY',completed=True,
            hardware_accepted=False,deployable=False,winner=None,confirmation_accessed=False,
            reason='No alternative passed all10 development holds and no-fault gate.',
            protocol_sha256=digest(HERE / 'protocol.json'), development_report_sha256=digest(HERE / 'development-report.json')))
        print('NO WINNER; stopped without confirmation, fitting or export.',flush=True)
        return
    winner = next(row for row in protocol['candidates'] if row['name']==eligible[0]['candidate'])
    frozen = dict(status='DEVELOPMENT_ONLY',hardware_accepted=False,deployable=False,winner=winner,
        protocol_sha256=digest(HERE / 'protocol.json'),development_report_sha256=digest(HERE / 'development-report.json'),
        selection=eligible[0],confirmation_not_yet_run=True)
    write_new(HERE / 'frozen-winner.json', frozen)
    print('FROZEN '+json.dumps(winner),flush=True)
    rows=[]
    for bias in protocol['confirmation']['encoder_bias_degrees']:
        for seed in protocol['confirmation']['seeds']:
            rows.append(episode(protocol['experiment'],winner['gains'],winner['name'],seed,bias,30.,'confirmation'))
    assert source_identity()==protocol['simulation_source']
    summary=summarize(winner['name'],rows)
    write_new(HERE / 'final-report.json',dict(status='DEVELOPMENT_ONLY',completed=True,
        hardware_accepted=False,deployable=False,winner=winner,confirmation_accessed=True,
        protocol_sha256=digest(HERE / 'protocol.json'),frozen_winner_sha256=digest(HERE / 'frozen-winner.json'),
        development_report_sha256=digest(HERE / 'development-report.json'),summary=summary,
        analytic_teacher_passed=bool(summary['episodes']==20 and summary['holds']==20 and summary['faults']==0),
        episodes=rows,neural_fit_performed=False,neural_export_performed=False))
    print(json.dumps(summary),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('declare','run'))
    args=parser.parse_args()
    declare() if args.mode=='declare' else run()
