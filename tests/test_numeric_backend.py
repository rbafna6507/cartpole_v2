"""Offline parity and failure boundaries for the optional numeric backend."""
from hashlib import sha256
import importlib
import json
import math
from pathlib import Path
import random
import subprocess
import sys

import pytest

from cartpole_sdk.contracts import ValidationError
from cartpole_sdk.policies.neural import NeuralPolicy, _digest
from cartpole_sdk.policies.rig_observation import rig_channels
from test_policy_sensor_contract import numeric_actor


ROOT = Path(__file__).resolve().parents[1]
ACTOR = ROOT / 'training/candidates/balance-20261020/actor.json'
TRACE = ROOT / 'evidence/balance-error-20261020/live/rig-1792544706721154771-3871944831.jsonl'


def backend_type():
    module = 'cartpole_sdk.policies.numeric_backend'
    assert importlib.util.find_spec(module) is not None, 'optional numeric backend is missing'
    return importlib.import_module(module).NumpyActorBackend


def encoded(values):
    return dict(age_s=values[:7], state=values[7:14], valid=values[14:])


def repin(actor):
    actor.pop('content_sha256', None)
    actor['content_sha256'] = _digest(actor)
    return actor


@pytest.fixture
def actors():
    pytest.importorskip('numpy')
    actor = json.loads(ACTOR.read_text())
    return actor, NeuralPolicy(actor, channels=rig_channels()), backend_type()(actor)


def test_frozen_actor_parity_for_random_boundaries_masks_and_feature_order(actors):
    actor, scalar, numeric = actors
    rng = random.Random(20261021)
    cases = [[0.] * 21, [1.] * 21, [-1.] * 21]
    # Each feature is excited separately, including ages and validity flags.
    for index in range(21):
        for value in (-1e6, -25., -1., -.02, 0., .02, 1., 25., 1e6):
            values = [0.] * 21
            values[index] = value
            cases.append(values)
    for _ in range(1500):
        theta = rng.uniform(-math.pi, math.pi)
        cases.append([rng.choice((-.001, 0., .02, .15, -1.)) for _ in range(7)] +
            [rng.uniform(-.31, .31), rng.uniform(-1.5, 1.5), math.sin(theta),
             math.cos(theta), rng.uniform(-150., 150.), rng.uniform(-25., 25.),
             rng.choice((-1., 0., 1.))] + [rng.choice((0., 1.)) for _ in range(7)])
    for _ in range(500):
        cases.append([rng.uniform(-1e3, 1e3) for _ in range(21)])
    for values in cases:
        features = encoded(values)
        assert numeric.predict_encoded(features) == pytest.approx(
            scalar.predict_encoded(features), rel=2e-13,
            abs=actor['action_scale_m_s2'] * 2e-13)


def test_reconstructed_real_action_observations_match_scalar_and_recorded_demands(actors):
    actor, scalar, numeric = actors
    records = [json.loads(line) for line in TRACE.read_text().splitlines()]
    states = {row['state']['unwrapped_tick']: row['state'] for row in records if row['type'] == 'state'}
    count = 0
    for row in records:
        if row['type'] != 'action_request':
            continue
        request = row['request']
        state = states[request['observation_sequence']]
        # Raw synchronous control_observation uses the same board effective time
        # for every channel, so all seven encoded ages are zero.
        features = dict(age_s=[0.] * 7, valid=[1] * 7, state=[state['x'],
            state['velocity'], math.sin(state['theta']), math.cos(state['theta']),
            state['omega'], state['acceleration'], state['brake_direction']])
        expected = scalar.predict_encoded(features)
        assert expected == pytest.approx(request['acceleration_m_s2'], abs=1e-12)
        assert numeric.predict_encoded(features) == pytest.approx(
            expected, rel=2e-13, abs=actor['action_scale_m_s2'] * 2e-13)
        count += 1
    assert count >= 7, 'exercise the complete recorded action sequence'


@pytest.mark.parametrize('demand, expected', [(-2., -3.), (-1., -3.), (-.25, -.75),
                                           (0., 0.), (.25, .75), (1., 3.), (2., 3.)])
def test_action_clips_before_scaling(demand, expected):
    pytest.importorskip('numpy')
    actor = numeric_actor('raw')
    actor['action_scale_m_s2'] = 3.
    actor['layers'][-1]['bias'][0] = demand
    assert backend_type()(repin(actor)).predict_encoded(encoded([0.] * 21)) == expected


@pytest.mark.parametrize('values', [[0.] * 20, [0.] * 22,
    [float('nan')] + [0.] * 20, [float('inf')] + [0.] * 20,
    [float('-inf')] + [0.] * 20])
def test_invalid_features_fail_closed_with_scalar_error(actors, values):
    _, scalar, numeric = actors
    for policy in (scalar, numeric):
        with pytest.raises(ValidationError, match='invalid actor features'):
            policy.predict_encoded(encoded(values))


@pytest.mark.parametrize('features, error', [({}, KeyError),
    ({'age_s': [None] * 7, 'state': [0.] * 7, 'valid': [1] * 7}, TypeError),
    ({'age_s': ['invalid'] * 7, 'state': [0.] * 7, 'valid': [1] * 7}, ValueError)])
def test_malformed_features_propagate_scalar_errors(actors, features, error):
    _, scalar, numeric = actors
    for policy in (scalar, numeric):
        with pytest.raises(error):
            policy.predict_encoded(features)


def test_nonfinite_affine_output_rejected_before_tanh_can_hide_overflow():
    pytest.importorskip('numpy')
    actor = numeric_actor('raw')
    actor['layers'][0]['weights'][0][0] = 1e6
    repin(actor)
    for policy in (NeuralPolicy(actor, channels=rig_channels()), backend_type()(actor)):
        with pytest.raises(ValidationError, match='nonfinite actor inference'):
            policy.predict_encoded(encoded([1e308] + [0.] * 20))


@pytest.mark.parametrize('problem', ['shape', 'bias', 'activation', 'coefficient', 'feature_order', 'hash'])
def test_actor_validation_is_not_bypassed(problem):
    pytest.importorskip('numpy')
    actor = numeric_actor('raw')
    if problem == 'shape': actor['layers'][0]['weights'][0].pop()
    if problem == 'bias': actor['layers'][1]['bias'].pop()
    if problem == 'activation': actor['layers'][0]['activation'] = 'relu'
    if problem == 'coefficient': actor['layers'][2]['weights'][0][0] = 1_000_001.
    if problem == 'feature_order': actor['feature_order'].reverse()
    repin(actor)
    if problem == 'hash': actor['content_sha256'] = '0' * 64
    with pytest.raises(ValidationError):
        backend_type()(actor)


def test_construction_snapshots_validated_weights_scale_and_feature_order(actors):
    actor, _, numeric = actors
    features = encoded([.1] * 21)
    expected = numeric.predict_encoded(features)
    provenance = numeric.provenance()
    actor['layers'][0]['weights'][0][0] = float('nan')
    actor['layers'][-1]['bias'][0] = 1e6
    actor['action_scale_m_s2'] = 25.
    actor['feature_order'].reverse()
    assert numeric.predict_encoded(features) == expected
    assert numeric.provenance() == provenance


def test_provenance_identifies_implementation_and_actor(actors):
    actor, _, numeric = actors
    module = importlib.import_module('cartpole_sdk.policies.numeric_backend')
    info = numeric.provenance()
    assert info['source_sha256'] == sha256(Path(module.__file__).read_bytes()).hexdigest()
    assert info['actor_content_sha256'] == actor['content_sha256']
    assert info['dtype'] == 'float64'
    assert info['numpy_version'] == importlib.import_module('numpy').__version__
    json.dumps(info, allow_nan=False)


def test_absent_optional_numpy_has_actionable_failure(monkeypatch):
    import builtins
    real_import = builtins.__import__
    def without_numpy(name, *args, **kwargs):
        if name == 'numpy':
            raise ModuleNotFoundError('NumPy intentionally absent')
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', without_numpy)
    with pytest.raises(ValidationError, match='NumPy'):
        backend_type()(numeric_actor('raw'))


def test_offline_benchmark_reports_parity_warmed_distributions_and_source_hashes(tmp_path):
    pytest.importorskip('numpy')
    script = ROOT / 'scripts/benchmark-numeric-inference.py'
    assert script.is_file(), 'reproducible offline benchmark is missing'
    destination = tmp_path / 'benchmark.json'
    replay = tmp_path / 'replay.json'
    subprocess.run([sys.executable, str(script), '--actor', str(ACTOR),
        '--trace', str(TRACE), '--samples', '12', '--warmup', '2', '--random-cases', '16',
        '--output', str(destination), '--save-replay', str(replay)], check=True, capture_output=True)
    result = json.loads(destination.read_text())
    assert result['parity']['real_action_cases'] >= 7
    assert result['parity']['max_abs_error_m_s2'] < 1e-10
    assert result['backend']['source_sha256']
    assert result['actor_file_sha256'] == sha256(ACTOR.read_bytes()).hexdigest()
    for name in ('scalar', 'numpy-einsum', 'numpy-matmul-comparison'):
        timing = result['timings_us'][name]
        assert timing['count'] == 12
        assert timing['min'] <= timing['p50'] <= timing['p95'] <= timing['p99'] <= timing['max']
    saved = json.loads(replay.read_text())
    assert saved['sources'][0]['sha256'] == sha256(TRACE.read_bytes()).hexdigest()
    assert len(saved['actions']) >= 7


def test_latest_103_action_trace_replay_fixture_matches_frozen_actor(actors):
    actor, scalar, numeric = actors
    fixture = ROOT / 'evidence/console-policy-20261021/numeric-replay-inputs.json'
    assert fixture.is_file(), 'latest recorded action encodings are missing'
    replay = json.loads(fixture.read_text())
    assert len(replay['actions']) == 103
    for action in replay['actions']:
        features = action['encoded']
        expected = scalar.predict_encoded(features)
        assert expected == pytest.approx(action['recorded_acceleration_m_s2'], rel=0., abs=1e-12)
        assert numeric.predict_encoded(features) == pytest.approx(expected,
            rel=2e-13, abs=actor['action_scale_m_s2'] * 2e-13)
