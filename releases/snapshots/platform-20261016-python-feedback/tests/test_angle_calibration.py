"""Independent count fixtures exercise calibration rejection and application gates."""
import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from cartpole_sdk.sensing import calibration as cal


def window(center, window_id="new-window"):
    return {'window_id': window_id, 'sampling': 'native', 'raw_counts': [(center + (i % 3 - 1)) % 4096 for i in range(64)],
            'sample_period_s': .01}


def dataset():
    pairs = []
    # Hand-checked: 2305 + 2048 + 113 == 370 modulo 4096.
    for split, count in [('train', 8), ('validation', 4)]:
        for i in range(count):
            pairs.append({'pair_id': f'{split}-{i}', 'session_id': f'{split}-session-{i // (count // 2)}',
                          'split': split, 'direction': 'positive' if i % 2 else 'negative',
                          'reference_uncertainty_counts': 1.,
                          'upright': window(370, f'{split}-{i}-up'), 'hanging': window(2305, f'{split}-{i}-down')})
    return {'schema_version': 1, 'hardware_id': 'rig-a', 'source_id': 'encoder-a',
            'frame_id': 'pole-upright', 'fixture_id': 'fixture-a', 'sensor_config_id': 'as5600-conf-768', 'counts_per_turn': 4096,
            'provenance': {'acquisition_version': 'test-v1', 'source': 'synthetic-test-fixture'},
            'pairs': pairs}


def fit(data=None):
    return cal.fit_calibration(dataset() if data is None else data)


def test_constant_offset_validates_but_requires_explicit_approval_and_identity():
    profile = fit()
    assert profile.status == 'validated'
    assert profile.offset_counts == 113
    with pytest.raises(ValueError, match='approv'):
        profile.upright_from_hanging(2305, hardware_id='rig-a', source_id='encoder-a', fixture_id='fixture-a', sensor_config_id='as5600-conf-768')
    approved = profile.approve(approved_by='operator', approved_at='2026-10-15T12:00:00Z')
    assert approved.upright_from_hanging(2305, hardware_id='rig-a', source_id='encoder-a', fixture_id='fixture-a', sensor_config_id='as5600-conf-768') == 370
    with pytest.raises(ValueError, match='identity'):
        approved.upright_from_hanging(2305, hardware_id='rig-b', source_id='encoder-a', fixture_id='fixture-a', sensor_config_id='as5600-conf-768')


def test_circular_math_and_wraparound_windows():
    assert cal.signed_count_delta(2, 4094, 4096) == 4
    assert cal.signed_count_delta(4094, 2, 4096) == -4
    assert cal.signed_count_delta(2048, 0, 4096) == -2048
    data = dataset()
    for pair in data['pairs']:
        pair['upright'] = window(0, pair['upright']['window_id'])
        pair['hanging'] = window(2038, pair['hanging']['window_id'])
    profile = fit(data).approve(approved_by='operator', approved_at='2026-10-15T12:00:00Z')
    assert profile.offset_counts == 10
    assert profile.upright_from_hanging(2038, hardware_id='rig-a', source_id='encoder-a', fixture_id='fixture-a', sensor_config_id='as5600-conf-768') == 0


def test_one_pair_is_insufficient_and_cannot_be_approved():
    data = dataset(); data['pairs'] = data['pairs'][:1]
    profile = fit(data)
    assert profile.status == 'insufficient_data'
    assert profile.offset_counts == 113
    with pytest.raises(ValueError, match='validated'):
        profile.approve(approved_by='operator', approved_at='2026-10-15T12:00:00Z')


def test_unstable_and_short_windows_are_visible_and_rejected():
    data = dataset()
    data['pairs'][0]['hanging']['raw_counts'] = list(range(64))
    data['pairs'][1]['upright']['raw_counts'] = [370] * 4
    profile = fit(data)
    assert profile.status == 'rejected'
    report = profile.to_dict()['validation']
    assert {row['pair_id'] for row in report['excluded_pairs']} == {'train-0', 'train-1'}


def test_outlier_cannot_drag_median_or_be_hidden_by_robust_fit():
    data = dataset(); data['pairs'][0]['upright'] = window(670)
    profile = fit(data)
    assert profile.offset_counts == 113
    assert profile.status == 'rejected'
    assert 'train-0' in profile.to_dict()['validation']['outlier_pair_ids']


def test_direction_hysteresis_is_reported_and_rejected():
    data = dataset()
    for pair in data['pairs']:
        if pair['direction'] == 'positive':
            pair['upright'] = window(400, pair['upright']['window_id'])
    profile = fit(data)
    assert profile.status == 'rejected'
    assert profile.to_dict()['validation']['direction_gap_counts'] == 30


def test_heldout_failure_and_session_leakage_are_rejected():
    data = dataset()
    for pair in data['pairs']:
        if pair['split'] == 'validation':
            pair['upright'] = window(380, pair['upright']['window_id'])
    assert fit(data).status == 'rejected'
    data = dataset(); data['pairs'][-1]['session_id'] = data['pairs'][0]['session_id']
    assert fit(data).status == 'rejected'
    assert any('session' in s for s in fit(data).to_dict()['validation']['reasons'])


def test_single_direction_has_insufficient_coverage():
    data = dataset()
    for pair in data['pairs']:
        pair['direction'] = 'negative'
    assert fit(data).status == 'insufficient_data'


def test_uncertain_reference_cannot_be_accepted_even_when_fit_is_perfect():
    data = dataset()
    for pair in data['pairs']:
        pair['reference_uncertainty_counts'] = 10
    assert fit(data).status == 'rejected'


@pytest.mark.parametrize('mutate', [
    lambda d: d.update(counts_per_turn=4095),
    lambda d: d.update(hardware_id=''),
    lambda d: d['pairs'][0]['upright']['raw_counts'].__setitem__(0, float('nan')),
    lambda d: d['pairs'][0]['upright']['raw_counts'].__setitem__(0, True),
    lambda d: d['pairs'][0]['upright'].update(sample_period_s=0),
    lambda d: d['pairs'][0].update(reference_uncertainty_counts=-1),
    lambda d: d['pairs'][0].update(direction='unknown'),
    lambda d: d['pairs'][1].update(pair_id=d['pairs'][0]['pair_id']),
])
def test_malformed_inputs_fail_closed(mutate):
    data = dataset(); mutate(data)
    with pytest.raises(ValueError):
        fit(data)


def test_reproducible_profile_and_serialization_revalidate_model_claims():
    profile = fit()
    data = dataset(); data['pairs'].reverse()
    assert fit(data).calibration_id == profile.calibration_id
    loaded = cal.CalibrationProfile.from_dict(profile.to_dict())
    assert loaded.to_dict() == profile.to_dict()
    for field, value in [('offset_counts', 114), ('calibration_id', 'forged')]:
        payload = profile.to_dict(); payload[field] = value
        with pytest.raises(ValueError, match='integrity'):
            cal.CalibrationProfile.from_dict(payload)
    payload = profile.to_dict(); payload['validation']['status'] = 'rejected'
    with pytest.raises(ValueError, match='integrity'):
        cal.CalibrationProfile.from_dict(payload)


def test_cli_fit_report_check_and_approve_are_offline(tmp_path):
    source = tmp_path / 'pairs.json'; target = tmp_path / 'profile.json'
    source.write_text(json.dumps(dataset()))
    command = [sys.executable, '-m', 'cartpole_sdk.sensing.calibration']
    result = subprocess.run(command + ['fit', str(source), '--output', str(target)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    report = subprocess.run(command + ['report', str(target)], capture_output=True, text=True)
    assert json.loads(report.stdout)['status'] == 'validated'
    check = ['check', str(target), '--hardware-id', 'rig-a', '--source-id', 'encoder-a', '--fixture-id', 'fixture-a', '--sensor-config-id', 'as5600-conf-768']
    assert subprocess.run(command + check, capture_output=True).returncode == 2
    approved = subprocess.run(command + ['approve', str(target), '--output', str(target),
        '--approved-by', 'operator', '--approved-at', '2026-10-15T12:00:00Z'], capture_output=True, text=True)
    assert approved.returncode == 0, approved.stderr
    assert subprocess.run(command + check, capture_output=True).returncode == 0


def test_duplicate_json_keys_and_invalid_policy_rejected(tmp_path):
    path = tmp_path / 'duplicate.json'; path.write_text('{"schema_version":1,"schema_version":2}')
    with pytest.raises(ValueError, match='duplicate'):
        cal.load_json(path)
    with pytest.raises(ValueError):
        cal.CalibrationPolicy(max_error_deg=float('inf'))
    with pytest.raises(ValueError):
        cal.CalibrationPolicy(min_train_pairs=1)


def test_native_window_reuse_and_resampling_cannot_manufacture_repeatability():
    data = dataset()
    data['pairs'][1]['upright']['window_id'] = data['pairs'][0]['upright']['window_id']
    with pytest.raises(ValueError, match='reused window'):
        fit(data)
    data = dataset(); data['pairs'][0]['hanging']['sampling'] = 'interpolated'
    profile = fit(data)
    assert profile.status == 'rejected'
    assert any('resampled' in reason for row in profile.to_dict()['validation']['excluded_pairs'] for reason in row['reasons'])


def test_slow_window_drift_rejected_even_inside_span_limit():
    data = dataset()
    data['pairs'][0]['upright']['raw_counts'] = [370] * 32 + [373] * 32
    profile = fit(data)
    assert profile.status == 'rejected'
    assert any('drift' in reason for row in profile.to_dict()['validation']['excluded_pairs'] for reason in row['reasons'])


def test_approval_and_configuration_tampering_cannot_pass_application_gate():
    profile = fit().approve(approved_by='operator', approved_at='2026-10-15T12:00:00Z')
    payload = profile.to_dict(); payload['approval']['calibration_id'] = 'another-profile'
    with pytest.raises(ValueError, match='calibration_id'):
        cal.CalibrationProfile.from_dict(payload)
    for key in ('fixture_id', 'source_id', 'sensor_config_id'):
        identity = dict(hardware_id='rig-a', source_id='encoder-a', fixture_id='fixture-a', sensor_config_id='as5600-conf-768')
        identity[key] = 'changed'
        with pytest.raises(ValueError, match='identity'):
            profile.approved_offset_counts(**identity)
    payload = profile.to_dict(); payload['offset_counts'] = 1
    with pytest.raises(ValueError, match='integrity'):
        cal.CalibrationProfile(json.dumps(payload)).approved_offset_counts(
            hardware_id='rig-a', source_id='encoder-a', fixture_id='fixture-a', sensor_config_id='as5600-conf-768')


def test_policy_cannot_relax_required_acceptance_envelope():
    for parameters in ({'max_error_deg': 2}, {'max_direction_gap_counts': 50},
                       {'max_session_gap_counts': 50}, {'max_window_span_counts': 50},
                       {'min_window_samples': 8}, {'min_window_duration_s': .1}):
        with pytest.raises(ValueError):
            cal.CalibrationPolicy(**parameters)


def test_empty_measured_dataset_reports_insufficient_without_an_offset():
    data = dataset(); data['pairs'] = []
    profile = fit(data)
    assert profile.status == 'insufficient_data'
    assert profile.offset_counts is None
    assert profile.to_dict()['validation']['prediction_bound_counts']['validation'] is None


def test_correction_beyond_firmware_bound_is_rejected():
    data = dataset()
    for pair in data['pairs']:
        pair['upright'] = window(600, pair['upright']['window_id'])
    profile = fit(data)
    assert profile.status == 'rejected'
    assert any('bounded correction' in reason for reason in profile.to_dict()['validation']['reasons'])


def test_native_encoder_quantization_is_included_in_error_envelope():
    data = dataset()
    for pair in data['pairs']:
        if pair['split'] == 'validation':
            pair['upright'] = window(372, pair['upright']['window_id'])
    profile = fit(data)
    # 2 residual + 1 radius per pose + 1 reference + .5 quantization per pose = 6 counts.
    assert profile.status == 'rejected'
    assert profile.to_dict()['validation']['prediction_bound_counts']['validation'] == 6
