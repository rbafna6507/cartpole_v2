"""Training uses real SDK rollouts, disjoint held-out trials and safe artifacts."""
import importlib.util
import json
from dataclasses import asdict, replace
import pytest
from cartpole_sdk.contracts import Channel, ValidationError
from cartpole_sdk.policies import HostPolicyParameters
from cartpole_sdk.sim import SimulationConfig, SensorConfig


def api():
    assert importlib.util.find_spec('cartpole_sdk.learning.search'), 'episodic training is missing'
    from cartpole_sdk.learning import train, evaluate, save_artifact, load_policy
    return train, evaluate, save_artifact, load_policy


def channels():
    return tuple(Channel('cart' if q in ('position','velocity') else 'pole', q,
        'simulation','sim:upright+x') for q in ('position','velocity','angle','angular_velocity'))


def test_real_seeded_rollout_reproducibility_and_source_faults():
    _, evaluate, _, _ = api()
    config = SimulationConfig(control_steps=10, max_steps=20)
    a = evaluate(HostPolicyParameters(), seeds=(100,101), config=config)
    assert a == evaluate(HostPolicyParameters(), seeds=(100,101), config=config)
    assert len(a['episodes']) == 4  # each seed tests hanging and near-upright
    assert {e['start'] for e in a['episodes']} == {'hanging','upright'}
    assert all(e['steps'] == 20 for e in a['episodes'])
    bad = evaluate(HostPolicyParameters(), seeds=(100,), config=config,
                   sensors=SensorConfig(dropout_probability=1.))
    assert all(not e['success'] and e['fault_reason'] for e in bad['episodes'])
    assert all(e['steps'] == 0 for e in bad['episodes'])
    assert a['episodes'][0]['initial_state'] != a['episodes'][2]['initial_state']


def test_cem_is_deterministic_records_reward_selection_and_initial_weights(tmp_path):
    train, _, save, load = api()
    kw = dict(seed=7, training_seeds=(11,12), generations=1, population=4,
              config=SimulationConfig(control_steps=10,max_steps=15))
    a = train(**kw)
    assert a == train(**kw)
    assert a['training']['algorithm'] == 'cross_entropy_policy_search'
    assert a['training']['training_seeds'] == [11,12]
    assert a['training']['history'][0]['best_score'] >= a['training']['pretraining_score']
    assert a['training']['baseline_parameters'] == asdict(HostPolicyParameters())
    assert a['provenance']['code_sha256'] and a['provenance']['model_sha256']
    assert a['action_semantics'].startswith('raw acceleration')
    path = tmp_path/'policy.json'
    save(a,path)
    learned = load(path,channels=channels())
    assert asdict(learned.parameters) == a['parameters']
    assert learned.rate_hz == 100


def test_heldout_overlap_is_rejected_before_evaluation():
    train, evaluate, _, _ = api()
    artifact = train(seed=9, training_seeds=(21,), generations=1, population=4,
                     config=SimulationConfig(control_steps=4,max_steps=1))
    with pytest.raises(ValidationError, match='held.out'):
        evaluate(artifact, seeds=(21,30))


def test_numeric_json_only_and_schema_validation(tmp_path):
    train, _, save, load = api()
    artifact = train(training_seeds=(1,), generations=1, population=4,
                     config=SimulationConfig(control_steps=10,max_steps=1))
    path = tmp_path/'weights.json'
    for mutate in (lambda a:a.update(module='os.system'),
                   lambda a:a['parameters'].update(theta_gain='__import__("os")'),
                   lambda a:a['parameters'].update(theta_gain=float('nan')),
                   lambda a:a['parameters'].update(theta_gain=1e99),
                   lambda a:a.update(rate_hz=1000)):
        malformed = json.loads(json.dumps(artifact))
        mutate(malformed)
        path.write_text(json.dumps(malformed))
        with pytest.raises((ValidationError, ValueError)): load(path,channels=channels())
    path.write_text('{"schema":1,"schema":1}')
    with pytest.raises(ValidationError): load(path,channels=channels())
    path.write_bytes(b'0'*300_000)
    with pytest.raises(ValidationError): load(path,channels=channels())


def test_upright_host_controller_maintains_bounded_balance_in_governed_plant():
    _, evaluate, _, _ = api()
    result = evaluate(HostPolicyParameters(), seeds=(8,), starts=('upright',),
                      config=SimulationConfig(control_steps=10,max_steps=500))
    episode = result['episodes'][0]
    assert episode['success'], episode
    assert abs(episode['final_state']['theta']) < .15
    assert episode['max_abs_x_m'] < .2


def test_weight_loader_and_policy_require_no_simulator_on_hardware_host():
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    code = "import sys; sys.path.insert(0,'src'); from cartpole_sdk.learning import load_policy; from cartpole_sdk.policies import HostRatePolicy; assert 'numpy' not in sys.modules; assert 'mujoco' not in sys.modules"
    p = subprocess.run([sys.executable,'-S','-c',code],cwd=root,capture_output=True,text=True)
    assert p.returncode == 0, p.stderr
