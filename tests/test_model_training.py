"""Model-bound training never promotes scoped/rejected evidence to hardware."""
import importlib.util
import json
from dataclasses import asdict
from hashlib import sha256

import pytest

from cartpole_sdk.sim import SimulationConfig


def api():
    assert importlib.util.find_spec('cartpole_sdk.learning.model_experiment'), 'model-bound admission is missing'
    from cartpole_sdk.learning.model_experiment import load_training_model
    return load_training_model


def canonical(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def save_model(tmp_path, **changes):
    model = dict(schema='cartpole-development-model-v1', status='DEVELOPMENT_ONLY',
                 simulation_config=asdict(SimulationConfig(control_steps=10, max_steps=5)),
                 rationale='Synthetic software integration fixture, no physical evidence.',
                 limitations=['Not an identified model; no physical performance claim.'])
    model.update(changes)
    model['content_sha256'] = canonical(model)
    path = tmp_path / 'model.json'
    path.write_text(json.dumps(model))
    return path


def test_development_model_requires_conspicuous_opt_in_and_preserves_pin(tmp_path):
    load = api()
    path = save_model(tmp_path)
    with pytest.raises(ValueError, match='development-only'):
        load(path)
    admitted = load(path, development_only=True)
    assert admitted['simulation_config']['effective_length_m'] == .124
    assert admitted['model']['raw_sha256'] == sha256(path.read_bytes()).hexdigest()
    assert admitted['model']['acceptance_scope'] == 'DEVELOPMENT_ONLY'
    assert admitted['model']['accepted_fit'] is False
    assert admitted['hardware_accepted'] is False
    assert admitted['task_qualified'] is False


def test_tamper_rejected_fit_and_false_development_acceptance_are_rejected(tmp_path):
    load = api()
    path = save_model(tmp_path)
    raw = json.loads(path.read_text())
    raw['simulation_config']['effective_length_m'] = .2
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match='hash'):
        load(path, development_only=True)
    path = save_model(tmp_path, accepted_fit=True)
    with pytest.raises(ValueError, match='development model fields'):
        load(path, development_only=True)
    path.write_text(json.dumps(dict(schema='cartpole-id-fit-v1', accepted=False)))
    with pytest.raises(ValueError, match='export|schema'):
        load(path, development_only=True)


def test_identified_export_keeps_scope_and_never_implies_global_qualification(tmp_path):
    load = api()
    from cartpole_sdk.identification.workflow import export_model
    report = dict(accepted=True, kind='passive', model='viscous',
                  acceptance_scope='passive-down-conditional',
                  parameters=dict(effective_length_m=.18, angular_damping_per_s=.65,
                                  coulomb_rad_per_s2=0., angle_offset_rad=-.09))
    assumptions = dict(simulation_config=asdict(SimulationConfig(control_steps=10, max_steps=5)),
                       rationale='Synthetic exporter integration fixture, masses assumed.')
    path = tmp_path / 'accepted-scoped.json'
    export_model(report, scope='passive-down', assumptions=assumptions, output=path)
    with pytest.raises(ValueError, match='scope|qualification'):
        load(path)
    admitted = load(path, development_only=True)
    assert admitted['model']['acceptance_scope'] == 'passive-down'
    assert admitted['model']['accepted_fit'] is True
    assert admitted['task_qualified'] is False
    assert admitted['model']['fit_report_sha256'] == canonical(report)
    assert admitted['model']['assumptions'] == assumptions
    # A fresh outer pin must not hide a contradictory rejected nested report.
    raw = json.loads(path.read_text())
    raw['fit_report']['accepted'] = False
    raw.pop('content_sha256')
    raw['content_sha256'] = canonical(raw)
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match='fit report'):
        load(path, development_only=True)


def training_api():
    assert importlib.util.find_spec('cartpole_sdk.learning.model_search'), 'model-bound CEM is missing'
    from cartpole_sdk.learning.model_experiment import build_experiment
    from cartpole_sdk.learning.model_search import train, evaluate, read_artifact, save_artifact
    return build_experiment, train, evaluate, read_artifact, save_artifact


def experiment(tmp_path, **changes):
    build, *_ = training_api()
    from cartpole_sdk.control.parameters import ControllerParameters
    from cartpole_sdk.policies import HostPolicyParameters
    from cartpole_sdk.sim.rig_gym_env import RigObservationConfig
    args = dict(executor_parameters=asdict(ControllerParameters(bw=6., jmax=85.)),
                observation_config=asdict(RigObservationConfig()),
                prior_parameters=asdict(HostPolicyParameters()), development_only=True)
    args.update(changes)
    return build(save_model(tmp_path), **args)


def test_complete_snapshots_required_and_actual_governed_rollout_is_bound(tmp_path):
    _, train, evaluate, read, save = training_api()
    exp = experiment(tmp_path)
    assert exp['executor_parameters']['bw'] == 6.
    assert exp['executor_parameters']['jmax'] == 85.
    assert exp['observation_config']['encoder_counts'] == 4096
    with pytest.raises(ValueError, match='explicit fields'):
        experiment(tmp_path, executor_parameters={'bw': 6.})
    artifact = train(exp, seed=7, training_seeds=(11,), generations=1, population=4)
    assert artifact == train(exp, seed=7, training_seeds=(11,), generations=1, population=4)
    assert artifact['training']['algorithm'] == 'cross_entropy_policy_search'
    assert artifact['status'] == 'DEVELOPMENT_ONLY'
    assert artifact['hardware_accepted'] is False
    assert artifact['experiment'] == exp
    report = evaluate(artifact, seeds=(101,), trajectory=True)
    assert report['learned']['episodes_count'] == 2
    trace = report['learned']['episodes'][0]['trajectory']
    assert abs(trace[0]['executed_acceleration_m_s2']) <= .850001
    assert trace[0]['raw_acceleration_m_s2'] != trace[0]['executed_acceleration_m_s2']
    path = tmp_path / 'artifact.json'
    save(artifact, path)
    assert read(path) == artifact
    with pytest.raises(FileExistsError):
        save(artifact, path)
    from cartpole_sdk.learning.artifact import validate_artifact
    with pytest.raises(ValueError):
        validate_artifact(artifact)
    with pytest.raises(ValueError, match='overlap'):
        evaluate(artifact, seeds=(11, 101))


def test_observer_dropouts_fail_closed_without_using_truth_and_tamper_fails(tmp_path):
    _, train, evaluate, read, save = training_api()
    from cartpole_sdk.sim.rig_gym_env import RigObservationConfig
    exp = experiment(tmp_path, observation_config=asdict(RigObservationConfig(dropout_probability=1.)))
    artifact = train(exp, seed=7, training_seeds=(11,), generations=1, population=4)
    report = evaluate(artifact, seeds=(101,))
    # The rig preflight supplies one healthy initial snapshot; subsequent
    # dropout ends inference at the first unusable observation.
    assert all(e['steps'] == 1 and e['fault_reason'] for e in report['learned']['episodes'])
    path = tmp_path / 'artifact.json'
    save(artifact, path)
    malformed = json.loads(path.read_text())
    malformed['experiment']['executor_parameters']['jmax'] = 100.
    path.write_text(json.dumps(malformed))
    with pytest.raises(ValueError, match='hash'):
        read(path)


def test_ppo_help_requires_only_base_python_sdk():
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, '-S', '-c',
        "import sys,runpy; sys.path.insert(0,'src'); sys.argv=['train_ppo.py','--help']; "
        "runpy.run_path('examples/train_ppo.py',run_name='__main__')"],
        cwd=root, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert 'train' in result.stdout and 'evaluate' in result.stdout
