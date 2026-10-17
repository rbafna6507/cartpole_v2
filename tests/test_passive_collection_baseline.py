"""New passive collection measures hanging zero before inviting any release."""
from dataclasses import replace
import io
import json
import math
from unittest.mock import patch
import pytest
from cartpole_sdk.contracts import ValidationError
from cartpole_sdk.identification import experiments as probe
from test_system_id_experiments import scripted_rig


def camera_reader(clock):
    def sample():
        stamp = clock.now_ns // 20_000_000 * 20_000_000
        return dict(collector_received_ns=stamp, host_t=stamp/1e9+.01,
                    vision=dict(seq=stamp//20_000_000, t=stamp/1e9, detected=True,
                    stale=False, worker_error=None, age_since_host_read_s=.01, confidence=.9, image_angle_rad=.04,
                    pivot_px=[100.,100.], bob_px=[100+180*math.sin(.04),100+180*math.cos(.04)],
                    length_px=180., frame_width=960, frame_height=600))
    return sample


def test_passive_requires_camera_before_opening_serial_or_creating_run(tmp_path):
    with pytest.raises(ValueError, match='camera'):
        probe.collect('passive', output=tmp_path/'run', port='offline', camera_url=None,
                      rig_factory=lambda *a, **kw: pytest.fail('serial opened'))
    assert not (tmp_path/'run').exists()


def test_hanging_baseline_precedes_ready_and_does_not_change_upright_or_raw_angles():
    rig,clock=scripted_rig();rig._state=replace(rig.state, theta=math.pi-.11)
    events=[]
    def ready(event): events.append((clock.now_ns,event))
    with patch('cartpole_sdk.rig.client.time',clock),patch.object(probe,'time',clock):
        result=probe.run_passive(rig,seconds=1.,camera_read=camera_reader(clock),ready=ready)
    assert events[0][1]['status']=='measuring_hanging_baseline'
    recording=next((stamp,e) for stamp,e in events if e['status']=='recording')
    assert recording[0]>=2_000_000_000
    assert clock.now_ns>=3_000_000_000
    assert result['baseline']['encoder']['raw_angle_rad']==pytest.approx(math.pi-.11)
    assert result['baseline']['camera']['image_angle_rad']==pytest.approx(.04)
    assert recording[1]['hanging_zero_measured'] is True
    angles=[event for _,event in events if event['status']=='angles']
    assert angles and len(angles)<=3
    assert angles[0]['encoder_from_hanging_deg']==pytest.approx(0.)
    assert angles[0]['camera_from_hanging_deg']==pytest.approx(0.)
    baseline=next(r for r in rig.records if r['type']=='passive_baseline')
    assert baseline['baseline']==result['baseline']
    assert rig.state.theta==pytest.approx(math.pi-.11)
    assert rig.get_info().encoder_upright_raw==330
    assert all(c[1] not in ('ARM','MODE','HOME','REHOME','CLEAR','CALIBRATE','SET') for c in rig.commands)
    assert rig.commands[-1][1]=='STOP'


@pytest.mark.parametrize('failure',('missing','moving','interrupted'))
def test_bad_baseline_never_invites_release_and_stops(failure):
    rig,clock=scripted_rig();original=rig.wait_state;events=[]
    def wait(*a,**kw):
        state=original(*a,**kw)
        if clock.now_ns>=500_000_000:
            if failure=='moving':rig._state=replace(state,theta=math.pi+.1)
            elif failure=='interrupted':raise KeyboardInterrupt()
        return rig.state
    rig.wait_state=wait
    with patch('cartpole_sdk.rig.client.time',clock),patch.object(probe,'time',clock):
        with pytest.raises((ValidationError,KeyboardInterrupt)):
            probe.run_passive(rig,seconds=1.,camera_read=(lambda:None) if failure=='missing' else camera_reader(clock),ready=events.append)
    assert not any(e['status']=='recording' for e in events)
    assert not rig.state.enabled and rig.commands[-1][1]=='STOP'
    assert any(r['type']=='passive_failure' for r in rig.records)


def test_camera_clock_sync_records_roundtrip_bound_and_rejects_invalid_source():
    stamps=iter([1_000_000_000,1_004_000_000])
    with patch.object(probe.time,'monotonic_ns',side_effect=lambda:next(stamps)),patch('urllib.request.urlopen',return_value=io.BytesIO(b'{"monotonic_s": 0.5}')):
        value=probe.sample_camera_clock('http://camera.test:3090/api/sensing-stream?max_hz=100')
    assert value['offset_ns']==502_000_000
    assert value['uncertainty_ns']==2_000_000
    assert value['local_before_ns']==1_000_000_000
    with patch('urllib.request.urlopen',return_value=io.BytesIO(b'{"monotonic_s": "bad"}')):
        with pytest.raises(ValueError,match='clock'):probe.sample_camera_clock('http://camera.test/api/sensing-stream')


def test_baseline_window_starts_after_slow_parameter_readback():
    rig,clock=scripted_rig();get_parameters=rig.get_parameters;events=[]
    def slow_parameters():
        values=get_parameters()
        for _ in range(80):rig.wait_state()
        return values
    rig.get_parameters=slow_parameters
    with patch('cartpole_sdk.rig.client.time',clock),patch.object(probe,'time',clock):
        result=probe.run_passive(rig,seconds=1.,camera_read=camera_reader(clock),ready=events.append)
    assert result['baseline']['window_host_ns'][0]>=800_000_000
    assert result['baseline']['window_host_ns'][1]>=2_800_000_000
