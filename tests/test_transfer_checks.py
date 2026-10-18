"""Offline transfer checks must expose perturbations and terminal fault behavior."""
import importlib.util
import json
import random
from hashlib import sha256

import numpy as np
import pytest
torch = pytest.importorskip('torch')
pytest.importorskip('stable_baselines3')
from test_ppo_training import make_experiment


def api():
    assert importlib.util.find_spec('cartpole_sdk.learning.transfer_checks'), 'transfer evaluator missing'
    from cartpole_sdk.learning import transfer_checks
    return transfer_checks


class ZeroModel:
    """An explicit stationary-demand baseline, not a simulated success oracle."""
    def __init__(self):
        self.policy = torch.nn.Linear(1, 1)

    def predict(self, observation, deterministic):
        assert deterministic
        return np.array([0.], dtype=np.float32), None


def test_suite_records_actual_perturbations_without_changing_admitted_model(tmp_path):
    m = api(); exp = make_experiment(tmp_path)
    original = json.dumps(exp, sort_keys=True)
    report = m.run_suite(ZeroModel(), exp, tmp_path/'suite', seeds=(701,), seconds=.05,
        checkpoint_sha256='a'*64, source_binding={'caller': 'explicit synthetic baseline'})
    assert json.dumps(exp, sort_keys=True) == original
    rows = {(r['scenario'], r['start']): r for r in report['episodes']}
    nominal = rows['nominal', 'upright']['episode_parameters']['simulation_config']
    short = rows['length-minus5', 'upright']['episode_parameters']['simulation_config']
    assert short['effective_length_m'] == pytest.approx(nominal['effective_length_m']*.95)
    assert short['hinge_damping'] == pytest.approx(nominal['hinge_damping']*.95**2)
    assert rows['delay-8-2', 'hanging']['episode_parameters']['observation_config']['telemetry_delay_steps'] == 8
    assert report['hardware_accepted'] is False and report['deployable'] is False
    assert report['runner_replay']['status'] == 'outstanding'
    assert all(not r['hold_success'] and not r['final_window_complete'] for r in report['episodes'])
    recipe = tmp_path/'suite'/'recipe.json'
    assert report['recipe_sha256'] == sha256(recipe.read_bytes()).hexdigest()
    for row in report['episodes']:
        trace = tmp_path/'suite'/row['trace_path']
        assert sha256(trace.read_bytes()).hexdigest() == row['trace_sha256']
    with pytest.raises(FileExistsError):
        m.run_suite(ZeroModel(), exp, tmp_path/'suite', seeds=(701,), seconds=.05,
            checkpoint_sha256='a'*64, source_binding={'caller': 'synthetic'})


def test_fault_scenarios_are_fault_response_checks_not_balance_passes(tmp_path):
    m = api(); exp = make_experiment(tmp_path)
    report = m.run_suite(ZeroModel(), exp, tmp_path/'suite', seeds=(701,), seconds=.05,
        checkpoint_sha256='a'*64, source_binding={'caller': 'synthetic'})
    rows = {(r['scenario'], r['start']): r for r in report['episodes']}
    for start in ('upright', 'hanging'):
        boundary = rows['delay-8-2', start]
        assert boundary['fault_reason'] is None
        expired = rows['delay-9-2-fault', start]
        assert expired['fault_reason'] == 'action lease expired'
        assert expired['final_state']['time_ns'] == 20_000_000
        assert expired['fault_response_pass'] is True and not expired['hold_success']
        dropout = rows['telemetry-invalid-fault', start]
        assert dropout['fault_reason'] is not None and dropout['fault_response_pass'] is True
        assert not dropout['hold_success']


def test_angle_offsets_only_change_actor_inputs_and_expose_action_sensitivity(tmp_path):
    m = api(); exp = make_experiment(tmp_path)
    report = m.run_suite(ZeroModel(), exp, tmp_path/'suite', seeds=(701,), seconds=.05,
        checkpoint_sha256='a'*64, source_binding={'caller': 'synthetic'})
    rows = {(r['scenario'], r['start']): r for r in report['episodes']}
    def trace(name):
        return [json.loads(line) for line in (tmp_path/'suite'/rows[name, 'upright']['trace_path']).read_text().splitlines()]
    nominal, offset = trace('nominal'), trace('angle-plus1deg')
    assert nominal[0]['ground_truth_after'] == offset[0]['ground_truth_after']
    a = nominal[0]['actor_observation']['state']; b = offset[0]['actor_observation']['state']
    assert np.arctan2(b[2], b[3])-np.arctan2(a[2], a[3]) == pytest.approx(np.pi/180)
    assert a[:2] == b[:2] and a[4:] == b[4:]
    assert offset[0]['unperturbed_raw_action_m_s2'] == offset[0]['requested_raw_action_m_s2'] == 0.


def test_suite_preserves_global_rng_weights_and_rejects_bad_source_pin(tmp_path):
    m = api(); exp = make_experiment(tmp_path); model = ZeroModel()
    random.seed(77); np.random.seed(78); torch.manual_seed(79)
    ps, ns, ts = random.getstate(), np.random.get_state(), torch.get_rng_state().clone()
    weights = {k: v.clone() for k, v in model.policy.state_dict().items()}
    m.run_suite(model, exp, tmp_path/'suite', seeds=(701,), seconds=.05,
        checkpoint_sha256='a'*64, source_binding={'evaluation_source': m.source_identity()})
    assert ps == random.getstate(); np.testing.assert_array_equal(ns[1], np.random.get_state()[1])
    assert torch.equal(ts, torch.get_rng_state())
    assert all(torch.equal(v, weights[k]) for k, v in model.policy.state_dict().items())
    with pytest.raises(ValueError, match='source'):
        m.run_suite(model, exp, tmp_path/'bad', seeds=(701,), seconds=.05,
            checkpoint_sha256='a'*64, source_binding={'evaluation_source': {}})
    assert not (tmp_path/'bad').exists()


def test_mutating_predictor_cannot_produce_completed_report_and_weights_are_restored(tmp_path):
    m = api(); exp = make_experiment(tmp_path)
    class MutatingModel(ZeroModel):
        def predict(self, observation, deterministic):
            with torch.no_grad():
                self.policy.weight.add_(1.)
            random.random(); np.random.random(); torch.rand(1)
            return super().predict(observation, deterministic)
    model = MutatingModel()
    before = {k:v.clone() for k,v in model.policy.state_dict().items()}
    ps, ns, ts = random.getstate(), np.random.get_state(), torch.get_rng_state().clone()
    with pytest.raises(ValueError, match='weights changed'):
        m.run_suite(model, exp, tmp_path/'mutated', seeds=(701,), seconds=.01,
            checkpoint_sha256='a'*64, source_binding={'caller': 'synthetic mutation probe'})
    assert not (tmp_path/'mutated'/'report.json').exists()
    assert all(torch.equal(v, before[k]) for k,v in model.policy.state_dict().items())
    assert ps == random.getstate(); np.testing.assert_array_equal(ns[1], np.random.get_state()[1])
    assert torch.equal(ts, torch.get_rng_state())


def test_command_sensitivity_uses_same_observation_counterfactual(tmp_path):
    m = api(); exp = make_experiment(tmp_path)
    class AngleModel(ZeroModel):
        def predict(self, observation, deterministic):
            return np.array([observation['state'][2]/25.]), None
    report = m.run_suite(AngleModel(), exp, tmp_path/'suite', seeds=(701,), seconds=.01,
        checkpoint_sha256='a'*64, source_binding={'caller': 'synthetic angle law'})
    row = next(r for r in report['episodes'] if r['scenario']=='angle-plus1deg' and r['start']=='upright')
    trace = json.loads((tmp_path/'suite'/row['trace_path']).read_text().splitlines()[0])
    angle = np.arctan2(trace['actor_observation']['state'][2], trace['actor_observation']['state'][3])
    expected = np.sin(angle)-np.sin(angle-np.pi/180)
    assert row['angle_offset_command_delta_max_m_s2'] == pytest.approx(expected)
    assert row['angle_offset_command_delta_max_m_s2'] > .017
    assert trace['observation_available_ns'] <= trace['simulation_time_ns']


@pytest.mark.parametrize('steps, expected', [(499, False), (500, True)])
def test_final_hold_requires_all_five_seconds_of_actual_physics(tmp_path, steps, expected):
    m = api(); exp = make_experiment(tmp_path)
    from cartpole_sdk.learning.ppo import TrainingEnv
    class StationaryEnv(TrainingEnv):
        def initial_state(self, episode_seed, start):
            return 0., 0., 0., 0.
    exp['simulation_config']['max_steps'] = steps
    env = StationaryEnv(exp, (701,))
    (tmp_path/'traces').mkdir()
    try:
        row = m._episode(ZeroModel(), env, seed=701, start='upright',
            scenario=m.scenarios(exp)[0], root=tmp_path)
    finally:
        env.close()
    assert row['hold_success'] is expected
    assert row['final_window_complete'] is expected
    assert row['final_state']['time_ns'] == steps*10_000_000
    assert row['first_one_second_capture_s'] == pytest.approx(1.)


@pytest.mark.parametrize('pin', ['', 'a'*63, 'z'*64])
def test_checkpoint_pin_is_required_before_output_creation(tmp_path, pin):
    m = api()
    with pytest.raises(ValueError, match='checkpoint'):
        m.run_suite(ZeroModel(), make_experiment(tmp_path), tmp_path/'bad', seeds=(701,), seconds=.05,
            checkpoint_sha256=pin, source_binding={'caller': 'synthetic'})
    assert not (tmp_path/'bad').exists()
