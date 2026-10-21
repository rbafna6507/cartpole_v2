#!/usr/bin/env python3
"""Export the explicitly selected final balance seed47 actor; no hardware I/O."""
from hashlib import sha256
import json
from pathlib import Path

import torch

from cartpole_sdk.learning.balance_experiment import source_identity
from cartpole_sdk.learning.candidate_parity import check_candidate
from cartpole_sdk.learning.projected_ppo import EquilibriumPPO
from cartpole_sdk.policies.neural import load_neural_policy
from cartpole_sdk.policies.numeric_backend import NumpyActorBackend
from cartpole_sdk.policies.rig_observation import rig_channels

ROOT = Path(__file__).resolve().parents[3]
RUN = ROOT / 'runs/policy-confidence-20261021/balance/teacher-seed47'
OUT = ROOT / 'evidence/policy-confidence-20261021/hardware/export-balance47'
CANDIDATE = ROOT / 'training/candidates/balance-20261021-confidence'
CONFIRMATION = ROOT / 'runs/policy-confidence-20261021/balance-confirmation/teacher-seed47-step000020480/evaluation.json'


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def write_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def main():
    if OUT.exists() or CANDIDATE.exists():
        raise FileExistsError('export and candidate destinations must both be new')
    recipe = json.loads((RUN / 'recipe.json').read_text())
    report = json.loads((RUN / 'report.json').read_text())
    assert report['completed']
    assert all(report.get(key) == value for key, value in recipe.items())
    assert digest(RUN / 'recipe.json') == report['recipe_sha256']
    assert digest(RUN / 'source.zip') == report['source_zip_sha256']
    assert source_identity() == recipe['provenance']
    assert recipe['optimizer_seed'] == 47 and recipe['initialization'] == 'teacher'
    assert recipe['constraint'] == 'equilibrium' and recipe['steps'] == 20480
    matches = [row for row in report['evaluations'] if row['steps'] == 20480]
    assert len(matches) == 1
    selected = matches[0]
    checkpoint = RUN / selected['checkpoint']
    assert checkpoint.parent.resolve() == (RUN / 'checkpoints').resolve()
    assert digest(checkpoint) == selected['checkpoint_sha256']
    confirmation = json.loads(CONFIRMATION.read_text())
    assert confirmation['checkpoint_sha256'] == selected['checkpoint_sha256']
    assert confirmation['seconds'] == 60. and len(confirmation['episodes']) == 8
    assert all(row['steps'] == 6000 and row['hold_success'] and row['fault_reason'] is None
               for row in confirmation['episodes'])
    assert set((94000, 94007)).issubset(confirmation['seeds'])
    torch.set_num_threads(1)
    model = EquilibriumPPO.load(checkpoint, device='cpu')
    assert model.num_timesteps == 20480
    parity = check_candidate(model, recipe['experiment'], OUT,
        checkpoint_sha256=selected['checkpoint_sha256'], seeds=(94000, 94007), seconds=10.)
    assert parity['emission_parity_pass'] and parity['rejected_inputs'] == 0
    assert source_identity() == recipe['provenance']
    assert digest(checkpoint) == selected['checkpoint_sha256']
    actor_path = OUT / 'actor.json'
    policy = load_neural_policy(actor_path, channels=rig_channels(angle_source='raw', angle_frame_id='encoder-zero'))
    backend = NumpyActorBackend(policy.actor)
    assert policy.actor['status'] == 'DEVELOPMENT_ONLY' and not policy.actor['hardware_accepted']
    assert policy.actor['checkpoint_sha256'] == selected['checkpoint_sha256']
    count, maximum, saved_maximum = 0, 0., 0.
    for episode in parity['episodes']:
        trace = OUT / episode['trace_path']
        assert digest(trace) == episode['trace_sha256']
        for line in trace.read_text().splitlines():
            row = json.loads(line)
            scalar = policy.predict_encoded(row['encoded_observation'])
            numeric = backend.predict_encoded(row['encoded_observation'])
            maximum = max(maximum, abs(numeric - scalar))
            saved_maximum = max(saved_maximum, abs(scalar - row['sdk_raw_action_m_s2']))
            count += 1
    assert count == parity['compared_actions']
    assert maximum <= 1e-5 and saved_maximum <= 1e-5
    numpy_report = dict(schema='cartpole-candidate-numpy-replay-parity-v1', status='DEVELOPMENT_ONLY',
        completed=True, hardware_accepted=False, deployable=False, simulation_only=True,
        actor_file_sha256=digest(actor_path), actor_content_sha256=policy.actor['content_sha256'],
        checkpoint_sha256=selected['checkpoint_sha256'], replay_observations=count,
        raw_absolute_tolerance_m_s2=1e-5, max_abs_numpy_vs_strict_sdk_m_s2=maximum,
        max_abs_replayed_sdk_vs_saved_sdk_m_s2=saved_maximum, parity_pass=True,
        strict_loader='cartpole_sdk.policies.neural.load_neural_policy with current source hash checks',
        backend=backend.provenance(), trace_hashes={row['trace_path']: row['trace_sha256'] for row in parity['episodes']})
    write_new(OUT / 'numpy-replay-parity.json', numpy_report)
    binding = dict(schema='cartpole-balance-hardware-candidate-binding-v1', status='DEVELOPMENT_ONLY',
        completed=True, hardware_accepted=False, deployable=False, simulation_only=True,
        source_run=str(RUN), selected_step=20480, selected_optimizer_seed=47,
        selection='Explicit requested seed47 final checkpoint; no new candidate selection or reserved seeds used.',
        checkpoint_path=str(checkpoint), checkpoint_sha256=selected['checkpoint_sha256'],
        training_recipe_sha256=report['recipe_sha256'], training_report_sha256=digest(RUN / 'report.json'),
        training_source_zip_sha256=report['source_zip_sha256'], training_provenance=recipe['provenance'],
        current_training_source_matches=True, confirmation_path=str(CONFIRMATION),
        confirmation_sha256=digest(CONFIRMATION), confirmation_summary=confirmation['by_start'],
        reused_parity_seeds=[94000,94007], parity_seconds=10.,
        parity_starts=['upright','hanging'], parity_role='Emission check on already inspected seeds; not new held-out evidence.',
        parity_recipe_sha256=digest(OUT / 'recipe.json'), parity_report_sha256=digest(OUT / 'report.json'),
        numpy_parity_report_sha256=digest(OUT / 'numpy-replay-parity.json'),
        actor_file_sha256=digest(actor_path), actor_content_sha256=policy.actor['content_sha256'],
        actor_runtime_sha256=policy.actor['runtime_sha256'], executor_parameters=policy.actor['executor_parameters'],
        preparation_script_sha256=digest(Path(__file__)),
        hardware_scope='No live device access, parameter changes, homing, reference changes, or physical trials performed by this export.')
    write_new(OUT / 'binding.json', binding)
    CANDIDATE.mkdir(parents=True, exist_ok=False)
    with (CANDIDATE / 'actor.json').open('xb') as stream:
        stream.write(actor_path.read_bytes())
    assert digest(CANDIDATE / 'actor.json') == digest(actor_path)
    load_neural_policy(CANDIDATE / 'actor.json', channels=rig_channels())
    write_new(CANDIDATE / 'receipt.json', dict(status='DEVELOPMENT_ONLY', hardware_accepted=False,
        deployable=False, actor_file_sha256=digest(actor_path), actor_content_sha256=policy.actor['content_sha256'],
        checkpoint_sha256=selected['checkpoint_sha256'], binding_path=str(OUT / 'binding.json'),
        binding_sha256=digest(OUT / 'binding.json')))
    print(json.dumps(dict(actor=str(CANDIDATE / 'actor.json'), actor_file_sha256=digest(actor_path),
        actor_content_sha256=policy.actor['content_sha256'], checkpoint_sha256=selected['checkpoint_sha256'],
        binding_sha256=digest(OUT / 'binding.json'), compared_actions=parity['compared_actions'],
        sb3_sdk_max_error=parity['max_abs_raw_discrepancy_m_s2'], numpy_sdk_max_error=maximum,
        task_hold_successes=parity['task_hold_successes'], emission_parity_pass=parity['emission_parity_pass']), indent=2))


if __name__ == '__main__':
    main()
