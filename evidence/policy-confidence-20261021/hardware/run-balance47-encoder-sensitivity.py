#!/usr/bin/env python3
"""Fixed-actor development diagnosis of upstream encoder reference sensitivity."""
from dataclasses import asdict, replace
from hashlib import sha256
import json
import math
from pathlib import Path

import numpy as np
import torch

from cartpole_sdk.learning.balance_experiment import source_identity as training_sources
from cartpole_sdk.learning.candidate_parity import _episode, model_weights_sha256, source_identity
from cartpole_sdk.learning.model_experiment import validate_experiment
from cartpole_sdk.learning.projected_ppo import EquilibriumPPO
from cartpole_sdk.sim.rig_gym_env import RigCartpoleEnv

ROOT = Path(__file__).resolve().parents[3]
RUN = ROOT / 'runs/policy-confidence-20261021/balance/teacher-seed47'
EXPORT = ROOT / 'evidence/policy-confidence-20261021/hardware/export-balance47'
ACTOR = ROOT / 'training/candidates/balance-20261021-confidence/actor.json'
OUT = ROOT / 'evidence/policy-confidence-20261021/hardware/balance47-encoder-sensitivity'
SEEDS = (94000, 94007)
OFFSETS = (0., -.25, .25, -.5, .5, -1., 1.)


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def write_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def metrics(rows, episode):
    advanced = [row for row in rows if row['physical_time_advanced']]
    states = [row['ground_truth_after'] for row in advanced]
    raw = np.array([row['sdk_raw_action_m_s2'] for row in rows if row['sdk_raw_action_m_s2'] is not None])
    def elapsed(state):
        return (state['time_ns'] - episode['reset_warmup_ns']) / 1e9
    def exit_time(predicate):
        return next((elapsed(state) for state in states if predicate(state)), None)
    def rms(values):
        return float(np.sqrt(np.mean(np.square(values)))) if len(values) else None
    complete = episode['full_horizon_complete']
    tail = states[-500:] if complete and len(states) >= 500 else []
    x = np.array([state['x'] for state in states])
    tail_x = np.array([state['x'] for state in tail])
    balanced = [abs(state['theta']) < .15 and abs(state['omega']) < 1 and abs(state['x']) < .12 for state in states]
    return dict(first_exit_balance_s=exit_time(lambda state: not (abs(state['theta']) < .15 and abs(state['omega']) < 1 and abs(state['x']) < .12)),
        first_exit_cart_bound_s=exit_time(lambda state: abs(state['x']) >= .12),
        first_exit_angle_bound_s=exit_time(lambda state: abs(state['theta']) >= .15),
        first_exit_rate_bound_s=exit_time(lambda state: abs(state['omega']) >= 1.),
        all_decisions_balanced=bool(complete and all(balanced)),
        balanced_fraction_of_requested_horizon=sum(balanced) / 1000,
        true_x_rms_m=rms(x), final_window_x_rms_m=rms(tail_x),
        final_window_x_mean_m=float(np.mean(tail_x)) if len(tail_x) else None,
        final_window_x_peak_to_peak_m=float(np.ptp(tail_x)) if len(tail_x) else None,
        final_window_true_theta_mean_rad=float(np.mean([state['theta'] for state in tail])) if tail else None,
        whole_episode_centering_margin_m=.12 - episode['max_abs_x_m'],
        final_window_centering_margin_m=.12 - float(np.max(np.abs(tail_x))) if len(tail_x) else None,
        raw_command_count=len(raw), raw_command_min_m_s2=float(np.min(raw)) if len(raw) else None,
        raw_command_max_m_s2=float(np.max(raw)) if len(raw) else None,
        raw_command_rms_m_s2=rms(raw), raw_command_delta_rms_m_s2=rms(np.diff(raw)),
        command_clip_count=int(np.sum(np.abs(raw) >= 25. - 1e-9)),
        executed_acceleration_rms_m_s2=rms([row['executed_acceleration_m_s2'] for row in advanced]))


def main():
    if OUT.exists():
        raise FileExistsError(OUT)
    binding = json.loads((EXPORT / 'binding.json').read_text())
    original = json.loads((RUN / 'recipe.json').read_text())
    actor = json.loads(ACTOR.read_text())
    checkpoint = Path(binding['checkpoint_path'])
    assert digest(ACTOR) == binding['actor_file_sha256']
    assert digest(checkpoint) == binding['checkpoint_sha256'] == actor['checkpoint_sha256']
    assert digest(RUN / 'recipe.json') == binding['training_recipe_sha256']
    assert digest(RUN / 'source.zip') == binding['training_source_zip_sha256']
    assert training_sources() == original['provenance']
    config, parameters, observations, _ = validate_experiment(original['experiment'])
    assert observations.encoder_bias_rad == 0.
    assert observations.angle_source == 'raw'
    config = replace(config, max_steps=1000)
    torch.set_num_threads(1)
    model = EquilibriumPPO.load(checkpoint, device='cpu')
    before = model_weights_sha256(model)
    sources = source_identity()
    OUT.mkdir(parents=True, exist_ok=False)
    recipe = dict(schema='cartpole-fixed-actor-encoder-sensitivity-v1', status='DEVELOPMENT_ONLY',
        simulation_only=True, hardware_accepted=False, deployable=False,
        actor_path=str(ACTOR), actor_file_sha256=digest(ACTOR), actor_content_sha256=actor['content_sha256'],
        checkpoint_path=str(checkpoint), checkpoint_sha256=digest(checkpoint), model_weights_sha256=before,
        training_recipe_sha256=digest(RUN / 'recipe.json'), training_source_archive_path=str(RUN / 'source.zip'),
        training_source_zip_sha256=digest(RUN / 'source.zip'), training_provenance=original['provenance'],
        export_binding_sha256=digest(EXPORT / 'binding.json'), evaluation_source=sources,
        script_sha256=digest(Path(__file__)), experiment=original['experiment'],
        evaluation_simulation_config=asdict(config), base_observation_config=asdict(observations),
        offsets_degrees=list(OFFSETS), seeds=list(SEEDS), starts=['upright'], seconds=10., workers=1, torch_threads=1,
        intervention='Set RigObservationConfig.encoder_bias_rad to the stated constant before noise, quantization and encoder observer. All other plant, sensor, executor, actor, lease and timing settings unchanged.',
        bias_sign='Positive adds to measured encoder angle: measured = true + bias + unchanged noise/errors before quantization.',
        matched_randomness='The same reset seed is reused at each offset, retaining the same initial state and per-tick random draw sequence while trajectories evolve.',
        hold_definition='Full 10s with no fault, entire final5s true abs(theta)<.15rad, abs(omega)<1rad/s, abs(x)<.12m.',
        first_exit_definition='First advanced 100Hz truth sample outside any original balance bound; null means no sampled exit.',
        centering_definition='0.12m minus maximum absolute true cart position; whole-episode and complete final5s reported separately.',
        role='Diagnosis on two already inspected development poses; no retraining, candidate selection or seeds96000+.',
        limitations=['Two initial poses at10s are a small, reused development sample, not a robustness estimate.',
                    'Zero-offset simulation quality does not qualify hardware or certify its reference, friction, delays or encoder calibration.',
                    'An early fault makes final-window centering metrics unavailable; full command/truth traces remain saved.'])
    write_new(OUT / 'recipe.json', recipe)
    episodes = []
    for index, degrees in enumerate(OFFSETS):
        trial_dir = OUT / f'offset-{index:02d}'
        (trial_dir / 'traces').mkdir(parents=True)
        changed = replace(observations, encoder_bias_rad=math.radians(degrees))
        env = RigCartpoleEnv(config, parameters=parameters, observation_config=changed, ttl_ms=original['experiment']['ttl_ms'])
        try:
            for seed in SEEDS:
                row, _, _ = _episode(model, env, ACTOR, trial_dir, seed=seed, start='upright', action_scale=actor['action_scale_m_s2'])
                trace = trial_dir / row['trace_path']
                assert digest(trace) == row['trace_sha256']
                rows = [json.loads(line) for line in trace.read_text().splitlines()]
                row.update(metrics(rows, row), encoder_bias_degrees=degrees,
                    encoder_bias_rad=changed.encoder_bias_rad, observation_config=asdict(changed),
                    trace_path=str(trace.relative_to(OUT)))
                if degrees == 0.:
                    prior = [json.loads(line) for line in (EXPORT / f'traces/upright-{seed}.jsonl').read_text().splitlines()]
                    keys = ('encoded_observation', 'sdk_raw_action_m_s2', 'ground_truth_after', 'actual_executor_raw_m_s2', 'executed_acceleration_m_s2')
                    assert len(rows) == len(prior)
                    assert all(all(new[key] == old[key] for key in keys) for new, old in zip(rows, prior))
                    row['zero_offset_matches_prior_export_exactly'] = True
                assert row['emission_parity_pass']
                episodes.append(row)
                write_new(trial_dir / f'upright-{seed}.json', row)
                print(json.dumps({key: row[key] for key in ('encoder_bias_degrees','seed','hold_success','first_exit_balance_s','max_abs_x_m','final_window_x_rms_m','simulator_fault_reason')}), flush=True)
        finally:
            env.close()
    assert source_identity() == sources and training_sources() == original['provenance']
    assert model_weights_sha256(model) == before and digest(ACTOR) == binding['actor_file_sha256']
    summary = []
    for degrees in OFFSETS:
        group = [row for row in episodes if row['encoder_bias_degrees'] == degrees]
        tails = [row['final_window_x_rms_m'] for row in group]
        summary.append(dict(encoder_bias_degrees=degrees, episodes=len(group), holds=sum(row['hold_success'] for row in group),
            faults=sum(row['simulator_fault_reason'] is not None or row['policy_fault_reason'] is not None for row in group),
            first_exits_s=[row['first_exit_balance_s'] for row in group],
            worst_max_abs_x_m=max(row['max_abs_x_m'] for row in group),
            mean_final_window_x_rms_m=float(np.mean(tails)) if all(value is not None for value in tails) else None,
            mean_raw_command_delta_rms_m_s2=float(np.mean([row['raw_command_delta_rms_m_s2'] for row in group]))))
    report = dict(schema=recipe['schema'], status='DEVELOPMENT_ONLY', completed=True,
        simulation_only=True, hardware_accepted=False, deployable=False, recipe_sha256=digest(OUT / 'recipe.json'),
        actor_file_sha256=digest(ACTOR), checkpoint_sha256=digest(checkpoint),
        model_weights_sha256_before=before, model_weights_sha256_after=model_weights_sha256(model),
        episode_count=len(episodes), compared_commands=sum(row['compared_actions'] for row in episodes),
        summary=summary, episodes=episodes, limitations=recipe['limitations'])
    write_new(OUT / 'report.json', report)
    print(json.dumps(dict(report=str(OUT / 'report.json'), report_sha256=digest(OUT / 'report.json'), summary=summary), indent=2))


if __name__ == '__main__':
    main()
