"""Offline campaign analysis must not turn timing proxies into physical truth."""
import importlib
import json
import math
from pathlib import Path

import numpy as np
import pytest

from cartpole_sdk.identification import campaign


def analysis():
    return importlib.import_module('cartpole_sdk.identification.campaign_analysis')


def recorded_campaign(path, *, role='training', gain=1000., lag=.02, sign=1., synthetic=False):
    """Analytic moving pivot, different source clocks, and delayed delivery."""
    path.mkdir()
    origin = 1_000_000_000_000
    def motion(t):
        return sign * .02 * math.sin(math.pi*(t-2))**2 if 2 <= t <= 3 else 0.
    rows = []
    for i in range(501):
        t = i / 100
        ns = origin + round(t*1e9)
        state = dict(sid=17, tick=i*10, us=i*10000, unwrapped_us=100_000_000+i*10000,
                     received_ns=ns+5_000_000, x=motion(t), theta=math.pi,
                     omega=0., velocity=0., acceleration=0., demand=0., last_seq=0,
                     flags=205, fault=0)
        rows.append(dict(type='state', host_monotonic_ns=ns+5_000_000, state=state))
        if 200 <= i < 400:
            rows.append(dict(type='driven_reference', host_monotonic_ns=ns,
                             host_policy_ns=ns, board_ns=100_000_000_000+round(t*1e9),
                             phase='driven_excitation' if i < 300 else 'feedback_cart_hold'))
    frames = []
    for i in range(251):
        t = i/50
        # Physical source sample has the requested optical/count shape lag.
        x = 400 + gain*motion(t-lag)
        frames.append(dict(collector_received_ns=origin+round(t*1e9)+30_000_000,
            vision=dict(seq=i, t=970+t, detected=True, stale=False, worker_error=None,
                        image_angle_rad=0., length_px=100., confidence=.99,
                        pivot_px=[x, 200.], bob_px=[x,300.],
                        frame_width=1280, frame_height=720,
                        cart_position_m=987654., theta=1234.)))
    for filename, values in [('rig.jsonl', rows), ('vision.ndjson', frames)]:
        (path/filename).write_text(''.join(json.dumps(v)+'\n' for v in values))
    def anchor(t):
        return dict(local_before_ns=origin+round(t*1e9)-1_000_000,
                    local_after_ns=origin+round(t*1e9)+1_000_000,
                    server_monotonic_s=970+t, offset_ns=30_000_000_000,
                    uncertainty_ns=1_000_000)
    camera = dict(clock_sync=dict(method='http-roundtrip-midpoint', start=anchor(0), end=anchor(5)))
    (path/'vision-report.json').write_text(json.dumps(camera))
    report = dict(schema=campaign.SCHEMA, synthetic=synthetic, completed=True,
        stop_confirmed=True, records_dropped=0, raw_log='rig.jsonl', dataset_role=role,
        run_label=path.name, camera=camera,
        trials=[dict(id='001-actuator', kind='actuator', started_ns=origin+1_000_000_000,
                     finished_ns=origin+4_500_000_000, completed=True,
                     trial=dict(amplitude_m=sign*.02))])
    (path/'report.json').write_text(json.dumps(report))
    campaign.seal(path)
    return path


def test_camera_clock_mapping_retains_roundtrip_uncertainty():
    a = analysis()
    sync = dict(start=dict(server_monotonic_s=10.,local_before_ns=39_998_000_000,
                           local_after_ns=40_002_000_000),
                end=dict(server_monotonic_s=20.,local_before_ns=50_000_000_000,
                         local_after_ns=50_004_000_000))
    mapped, metadata = a.map_camera_clock(np.array([10.,15.,20.]), sync)
    assert mapped == pytest.approx([40.,45.001,50.002])
    assert metadata['max_anchor_half_roundtrip_s'] == pytest.approx(.002)
    assert metadata['exposure_latency_identified'] is False
    with pytest.raises(ValueError, match='anchor'):
        a.map_camera_clock(np.array([5.]), sync)


def test_interpolation_does_not_bridge_missing_board_samples_or_extrapolate():
    result = analysis().bounded_interpolate([0.,.01,.1,.11], [0.,1.,10.,11.],
                                           [-.01,.005,.05,.105,.12])
    assert result[1] == pytest.approx(.5)
    assert result[3] == pytest.approx(10.5)
    assert np.isnan(result[[0,2,4]]).all()


def test_fit_uses_source_camera_clock_raw_geometry_and_freezes_validation(tmp_path):
    train = recorded_campaign(tmp_path/'train')
    heldout = recorded_campaign(tmp_path/'heldout', role='validation', gain=1200., sign=-1.)
    result = analysis().analyze_campaigns([train], [heldout])
    fit = result['frozen_pixel_count_model']
    # Board receipt is 5 ms later than its sample; camera has a 20 ms shape lag.
    assert fit['lag_s'] == pytest.approx(.015)
    assert fit['gain_px_per_counted_m'] == pytest.approx(1000., abs=.1)
    assert result['training'][0]['trials'][0]['rmse_px'] < .002
    validation = result['validation'][0]['trials'][0]
    assert validation['rmse_px'] > 1.
    assert validation['applied_gain_px_per_counted_m'] == fit['gain_px_per_counted_m']
    assert result['independent_metric_scale'] is False
    assert result['physical_actuator_latency_identified'] is False
    assert result['hardware_accepted'] is False
    assert result['validation'][0]['declared_dataset_role'] == 'validation'
    assert result['training'][0]['source_manifest_sha256']


def test_validation_cannot_enter_fit_and_duplicate_raw_sources_are_rejected(tmp_path):
    heldout = recorded_campaign(tmp_path/'heldout', role='validation')
    with pytest.raises(ValueError, match='training'):
        analysis().analyze_campaigns([heldout], [])
    train = recorded_campaign(tmp_path/'train')
    with pytest.raises(ValueError, match='duplicate'):
        analysis().analyze_campaigns([train, train], [])


def test_unsealed_or_synthetic_evidence_cannot_produce_a_fit(tmp_path):
    fake = recorded_campaign(tmp_path/'synthetic', synthetic=True)
    with pytest.raises(ValueError, match='synthetic'):
        analysis().analyze_campaigns([fake], [])
    actual = recorded_campaign(tmp_path/'actual')
    with (actual/'rig.jsonl').open('a') as stream:
        stream.write('{}\n')
    with pytest.raises(ValueError, match='integrity'):
        analysis().analyze_campaigns([actual], [])


def test_absent_clock_anchors_are_never_replaced_by_receipt_time(tmp_path):
    actual = recorded_campaign(tmp_path/'actual')
    report = json.loads((actual/'report.json').read_text())
    report['camera'] = {}
    (actual/'report.json').write_text(json.dumps(report))
    (actual/'vision-report.json').write_text('{}')
    (actual/'manifest.json').unlink()
    campaign.seal(actual)
    with pytest.raises(ValueError, match='clock'):
        analysis().analyze_campaigns([actual], [])


def test_outputs_are_exclusive_and_cannot_modify_sealed_sources(tmp_path):
    actual = recorded_campaign(tmp_path/'actual')
    with pytest.raises(ValueError, match='outside'):
        analysis().analyze_campaigns([actual], [], output=actual/'analysis', plot=False)
    output = tmp_path/'analysis'
    result = analysis().analyze_campaigns([actual], [], output=output, plot=False)
    assert json.loads((output/'analysis.json').read_text()) == result
    assert campaign.verify(actual) == (True, None)
    with pytest.raises(FileExistsError):
        analysis().analyze_campaigns([actual], [], output=output, plot=False)
