"""Exercise the actual SB3 exporter and dependency-free SDK actor together."""
import importlib.util
import json
import random
from hashlib import sha256

import numpy as np
import pytest
torch = pytest.importorskip('torch')
pytest.importorskip('stable_baselines3')
from stable_baselines3 import PPO
from test_ppo_training import make_experiment
from cartpole_sdk.learning.ppo import TrainingEnv


def api():
    assert importlib.util.find_spec('cartpole_sdk.learning.candidate_parity'), 'candidate parity checker missing'
    from cartpole_sdk.learning import candidate_parity
    return candidate_parity


def candidate(tmp_path, *, bias=None):
    experiment = make_experiment(tmp_path)
    env = TrainingEnv(experiment, (11,))
    try:
        model = PPO('MultiInputPolicy', env, seed=3, n_steps=8, batch_size=4,
            policy_kwargs=dict(net_arch=dict(pi=[64,64], vf=[64,64]), activation_fn=torch.nn.Tanh),
            device='cpu')
    finally:
        env.close()
    if bias is not None:
        with torch.no_grad():
            model.policy.action_net.weight.zero_()
            model.policy.action_net.bias.fill_(bias)
    return model, experiment


def test_actual_export_sdk_inference_and_simulator_use_identical_observations(tmp_path):
    m = api(); model, exp = candidate(tmp_path)
    original = json.dumps(exp, sort_keys=True)
    report = m.check_candidate(model, exp, tmp_path/'parity', checkpoint_sha256='a'*64,
        seeds=(901,), seconds=.05)
    assert report['emission_parity_pass'] is True
    assert report['max_abs_raw_discrepancy_m_s2'] <= 1e-5
    assert report['compared_actions'] == 10
    assert {r['start'] for r in report['episodes']} == {'upright', 'hanging'}
    assert all(not row['hold_success'] for row in report['episodes'])
    assert report['hardware_accepted'] is False and report['deployable'] is False
    assert report['host_firmware_stop_replay']['status'] == 'outstanding'
    assert 'not Jetson deadline guarantee' in report['inference_latency']['scope']
    assert report['inference_latency']['thread_cpu_ns']['count'] == 10
    assert json.dumps(exp, sort_keys=True) == original
    actor_path = tmp_path/'parity'/'actor.json'
    actor = json.loads(actor_path.read_text())
    assert actor['status'] == 'DEVELOPMENT_ONLY' and actor['hardware_accepted'] is False
    assert actor['checkpoint_sha256'] == 'a'*64
    assert report['actor_file_sha256'] == sha256(actor_path.read_bytes()).hexdigest()
    for row in report['episodes']:
        path = tmp_path/'parity'/row['trace_path']
        assert row['trace_sha256'] == sha256(path.read_bytes()).hexdigest()
        trace = [json.loads(line) for line in path.read_text().splitlines()]
        assert len(trace) == 5 and len(trace[0]['sdk_observation']['samples']) == 6
        assert trace[0]['sdk_observation']['available_ns'] <= trace[0]['ground_truth_after']['time_ns']


def test_exported_clipped_action_is_the_action_applied_to_the_governor(tmp_path):
    m = api(); model, exp = candidate(tmp_path, bias=2.)
    report = m.check_candidate(model, exp, tmp_path/'parity', checkpoint_sha256='b'*64,
        seeds=(902,), seconds=.02)
    assert report['emission_parity_pass'] and report['max_abs_raw_discrepancy_m_s2'] == 0.
    for row in report['episodes']:
        records = [json.loads(line) for line in (tmp_path/'parity'/row['trace_path']).read_text().splitlines()]
        assert all(r['sb3_raw_action_m_s2'] == r['sdk_raw_action_m_s2'] == 25. for r in records)
        assert all(r['actual_executor_raw_m_s2'] == 25. for r in records)
        assert records[0]['executed_acceleration_m_s2'] == pytest.approx(1.5, abs=1e-6)


def test_invalid_input_is_a_real_policy_rejection_and_not_emission_parity_pass(tmp_path):
    m = api(); model, exp = candidate(tmp_path)
    exp['observation_config']['dropout_probability'] = 1.
    report = m.check_candidate(model, exp, tmp_path/'parity', checkpoint_sha256='c'*64,
        seeds=(903,), seconds=.05)
    assert report['emission_parity_pass'] is False
    assert report['rejected_inputs'] == 2 and report['compared_actions'] == 2
    assert all(row['policy_fault_reason'] for row in report['episodes'])
    assert all(not row['hold_success'] for row in report['episodes'])
    for row in report['episodes']:
        records = [json.loads(line) for line in (tmp_path/'parity'/row['trace_path']).read_text().splitlines()]
        assert records[-1]['sdk_raw_action_m_s2'] is None
        assert records[-1]['ground_truth_after']['time_ns'] == records[-2]['ground_truth_after']['time_ns']


def test_rng_weights_modes_and_output_immutability(tmp_path):
    m = api(); model, exp = candidate(tmp_path)
    model.policy.train()
    before = m.model_weights_sha256(model)
    random.seed(51); np.random.seed(52); torch.manual_seed(53)
    ps, ns, ts = random.getstate(), np.random.get_state(), torch.get_rng_state().clone()
    out = tmp_path/'parity'
    report = m.check_candidate(model, exp, out, checkpoint_sha256='d'*64, seeds=(904,), seconds=.02)
    assert report['model_weights_sha256_before'] == report['model_weights_sha256_after'] == before
    assert model.policy.training is True and m.model_weights_sha256(model) == before
    assert random.getstate() == ps
    np.testing.assert_array_equal(ns[1], np.random.get_state()[1])
    assert torch.equal(ts, torch.get_rng_state())
    with pytest.raises(FileExistsError):
        m.check_candidate(model, exp, out, checkpoint_sha256='d'*64, seeds=(904,), seconds=.02)


def test_invalid_checkpoint_pin_does_not_create_output(tmp_path):
    m = api(); model, exp = candidate(tmp_path)
    with pytest.raises(ValueError, match='checkpoint'):
        m.check_candidate(model, exp, tmp_path/'bad', checkpoint_sha256='wrong', seeds=(904,), seconds=.02)
    assert not (tmp_path/'bad').exists()


def test_disagreement_fails_parity_but_reference_action_never_drives_plant(tmp_path):
    m = api(); model, exp = candidate(tmp_path, bias=0.)
    class IncorrectComparison:
        policy = model.policy
        def predict(self, observation, deterministic):
            return np.array([1.]), None
    report = m.check_candidate(IncorrectComparison(), exp, tmp_path/'parity',
        checkpoint_sha256='e'*64, seeds=(905,), seconds=.02)
    assert report['emission_parity_pass'] is False
    assert report['max_abs_raw_discrepancy_m_s2'] == 25.
    for row in report['episodes']:
        records = [json.loads(line) for line in (tmp_path/'parity'/row['trace_path']).read_text().splitlines()]
        assert all(r['sb3_raw_action_m_s2'] == 25. and r['sdk_raw_action_m_s2'] == 0. for r in records)
        assert all(r['actual_executor_raw_m_s2'] == 0. for r in records)


@pytest.mark.parametrize('seconds, holds', [(4.99, 0), (5., 2)])
def test_hold_requires_full_five_seconds_separately_from_emission_parity(tmp_path, monkeypatch, seconds, holds):
    m = api(); model, exp = candidate(tmp_path, bias=0.)
    # A controlled exact-equilibrium initial condition; the real encoder,
    # numeric actor, governor and physics still execute every tick.
    monkeypatch.setattr(m, 'initial_state', lambda seed, start: (0.,0.,0.,0.))
    report = m.check_candidate(model, exp, tmp_path/'parity', checkpoint_sha256='f'*64,
        seeds=(906,), seconds=seconds)
    assert report['emission_parity_pass'] is True
    assert report['task_hold_successes'] == holds
    assert all(row['final_window_complete'] == (holds==2) for row in report['episodes'])
    assert all(row['final_state']['time_ns'] == round(seconds*1e9) for row in report['episodes'])
