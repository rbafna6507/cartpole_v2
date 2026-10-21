"""Fast numeric execution retains the same balance runner and leases."""
from unittest.mock import patch
import pytest
from cartpole_sdk.contracts import ValidationError
from cartpole_sdk.learning.balance_hardware import _load_policy
from test_balance_hardware import saved_actor, rehearsal, run


def test_numpy_prediction_matches_scalar_and_records_backend(tmp_path):
    path = saved_actor(tmp_path, demand=.123, action_scale=25.)
    scalar = _load_policy(path, inference_backend='python')
    fast = _load_policy(path, inference_backend='numpy')
    encoded = dict(age_s=[0.]*7, state=[0., 0., 0., 1., 0., 0., 0.], valid=[1]*7)
    assert fast.predict_encoded(encoded) == pytest.approx(scalar.predict_encoded(encoded), abs=1e-12)
    with rehearsal() as rig:
        result = run(rig, path, execute=True, guard_profile='rig', max_acceleration=25.)
        record = next(r for r in rig.records if r['type'] == 'balance_only_boundary')
        assert record['inference_backend']['backend'] == 'numpy-einsum'
        assert record['inference_backend']['warmup_predictions'] == 64
        assert result['inference_backend']['backend'] == 'numpy-einsum'
        requests = [r['request'] for r in rig.records if r['type'] == 'action_request']
        assert requests and all(r['expires_at_ns']-r['issued_at_ns'] == 20_000_000 for r in requests)
        assert not rig.state.enabled


def test_invalid_backend_refused_before_serial(tmp_path):
    path = saved_actor(tmp_path)
    with pytest.raises(ValidationError, match='backend'):
        _load_policy(path, inference_backend='other')


def test_numpy_missing_never_silently_falls_back(tmp_path):
    path = saved_actor(tmp_path)
    with patch('cartpole_sdk.policies.numeric_backend.NumpyActorBackend', side_effect=ValidationError('NumPy missing')):
        with rehearsal() as rig:
            with pytest.raises(ValidationError, match='NumPy missing'):
                run(rig, path, execute=True)
            assert not any(c[1] == 'ARM' for c in rig.commands)
            assert not rig.state.enabled
