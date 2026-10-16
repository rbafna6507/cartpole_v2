import json
from pathlib import Path
import pytest
from cartpole_sdk.contracts import Session
from cartpole_sdk.sensing.vision import ClockMapping, VisionProvider, VisionHTTPClient


def fixture():
    rows=json.loads((Path(__file__).parents[1]/'archive/vision3/evidence/live-measurement-samples.json').read_text())
    return next(r for r in rows if r['angle_valid'])


def provider(snapshot):
    session=Session('vision-test','session-clock')
    mapping=ClockMapping('vision-host','session-clock',1_000_000_000)
    return VisionProvider(session, frame_id='calibrated-rig', clock_mapping=mapping, calibration=snapshot['calibration'])


def test_actual_vision_snapshot_preserves_distinct_effective_times_and_missing_cart_scale():
    snap=fixture();p=provider(snap)
    received=int((snap['t']+.05)*1e9)+1_000_000_000
    obs=p.observation(snap,received_ns=received,source_clock_id='vision-host')
    angle,omega,x,v=obs.samples
    assert angle.source=='vision' and angle.validity=='valid'
    assert angle.acquired_ns==int(snap['t']*1e9)+1_000_000_000
    assert omega.effective_ns==int(snap['omega_effective_t']*1e9)+1_000_000_000
    assert omega.effective_ns<angle.effective_ns
    assert x.value is None and x.validity!='valid'
    assert p.last_timing['host_read_to_result_ms']==snap['host_read_to_result_ms']
    assert obs.clock_id=='session-clock'


def test_calibration_change_requires_explicit_new_provider_reset():
    snap=fixture();p=provider(snap)
    snap['calibration']['home_angle_rad']+=.1
    with pytest.raises(ValueError,match='calibration'):
        p.observation(snap,received_ns=int((snap['t']+.05)*1e9)+1_000_000_000,source_clock_id='vision-host')


def test_wrong_clock_future_and_repeated_frames_rejected():
    snap=fixture();p=provider(snap);received=int((snap['t']+.05)*1e9)+1_000_000_000
    with pytest.raises(ValueError,match='clock'):
        p.observation(snap,received_ns=received,source_clock_id='unknown')
    with pytest.raises(ValueError,match='future|result'):
        p.observation(snap,received_ns=int(snap['t']*1e9),source_clock_id='vision-host')
    p.observation(snap,received_ns=received,source_clock_id='vision-host')
    with pytest.raises(ValueError,match='increase|repeated'):
        p.observation(snap,received_ns=received+1,source_clock_id='vision-host')


def test_stale_sample_is_explicitly_invalid_even_if_snapshot_says_valid():
    snap=fixture();p=provider(snap)
    obs=p.observation(snap,received_ns=int((snap['t']+1)*1e9)+1_000_000_000,source_clock_id='vision-host')
    assert all(s.validity!='valid' and s.value is None for s in obs.samples)


def test_cart_and_angle_validity_are_independent_and_units_are_si():
    snap=fixture();snap['angle_valid']=False;snap['theta_rad']=None
    snap['calibration'].update(cart_a_px=[0,0],cart_b_px=[100,0],cart_span_mm=500)
    snap.update(cart_valid=True,cart_x_m=.123,cart_v_m_s=.2,cart_velocity_effective_t=snap['t']-.02)
    p=provider(snap);obs=p.observation(snap,received_ns=int((snap['t']+.05)*1e9)+1_000_000_000,source_clock_id='vision-host')
    assert obs.samples[0].validity=='invalid'
    assert obs.samples[2].value==.123 and obs.samples[2].unit=='m'
    assert obs.samples[3].value==.2 and obs.samples[3].unit=='m/s'


def test_clock_mapping_is_never_implicit_and_http_is_read_only():
    snap=fixture()
    with pytest.raises(ValueError,match='clock'):
        VisionProvider(Session('v','c'),frame_id='f',clock_mapping=None,calibration=snap['calibration'])
    with pytest.raises(ValueError,match='http'):
        VisionHTTPClient('file:///tmp/no')


def test_http_fetch_uses_strict_json_and_bounded_body(monkeypatch):
    import io
    import cartpole_sdk.sensing.vision as vision
    monkeypatch.setattr(vision,'urlopen',lambda *a,**kw:io.BytesIO(b'{"theta_rad":1.0}'))
    assert VisionHTTPClient('http://localhost/state').fetch()['theta_rad']==1.
    with pytest.raises(ValueError,match='byte limit'):
        VisionHTTPClient('http://localhost/state',max_bytes=5).fetch()
    monkeypatch.setattr(vision,'urlopen',lambda *a,**kw:io.BytesIO(b'{"t":1,"t":2}'))
    with pytest.raises(ValueError,match='duplicate'):
        VisionHTTPClient('http://localhost/state').fetch()


def test_future_velocity_effective_time_and_nan_measurement_rejected():
    snap=fixture();p=provider(snap);received=int((snap['t']+.05)*1e9)+1_000_000_000
    snap['omega_effective_t']=snap['t']+.1
    with pytest.raises(ValueError,match='future effective'):
        p.observation(snap,received_ns=received,source_clock_id='vision-host')
    snap=fixture();p=provider(snap);snap['theta_rad']=float('nan')
    with pytest.raises(ValueError,match='finite'):
        p.observation(snap,received_ns=received,source_clock_id='vision-host')
