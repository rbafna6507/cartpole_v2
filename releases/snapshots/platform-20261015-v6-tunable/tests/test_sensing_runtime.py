"""Maintained runtime's lean endpoint must retain the SDK source contract."""
import pytest

pytest.importorskip('cv2')
pytest.importorskip('flask')
from cartpole_vision.app import Engine, create_app
from cartpole_sdk.contracts import Session
from cartpole_sdk.sensing.vision import ClockMapping, VisionProvider


def test_measurement_endpoint_preserves_sdk_clock_calibration_frame_and_stale_semantics(monkeypatch):
    import cartpole_vision.app as runtime
    now=[100.03]
    monkeypatch.setattr(runtime.time,'monotonic',lambda:now[0])
    engine=Engine()
    estimator=engine.estimator
    estimator.last_t=100.
    estimator.home_angle=.01;estimator.home_length=150.
    estimator.cart_a=[0.,0.];estimator.cart_b=[100.,0.];estimator.cart_span_mm=500.
    estimator.last_state=dict(t=100.,seq=42,theta_rad=.2,omega_rad_s=.3,
        omega_effective_t=99.98,angle_valid=True,cart_valid=True,calibrated=True,
        cart_x_m=.1,cart_v_m_s=.2,cart_velocity_effective_t=99.97,
        frame_width=960,frame_height=600,detector_width=640,host_read_to_result_ms=10.)
    def expensive_diagnostics(*args,**kwargs):raise AssertionError('SDK request entered full diagnostic snapshot')
    engine.snapshot=expensive_diagnostics
    client=create_app(engine).test_client()
    response=client.get('/api/state?measurement=1')
    assert response.status_code==200 and response.headers['Cache-Control']=='no-store'
    snapshot=response.json
    assert (snapshot['seq'],snapshot['frame_width'],snapshot['frame_height'],snapshot['detector_width'])==(42,960,600,640)
    assert snapshot['calibration']==estimator.calibration()
    assert not snapshot['stale']
    provider=VisionProvider(Session('measurement-test','host'),frame_id='explicit-camera-frame',
        clock_mapping=ClockMapping('camera-host','host',0),calibration=snapshot['calibration'])
    observation=provider.observation(snapshot,received_ns=100_030_000_000,source_clock_id='camera-host')
    angle,omega,x,v=observation.samples
    assert all(s.validity=='valid' and s.frame_id=='explicit-camera-frame' for s in observation.samples)
    assert angle.effective_ns==100_000_000_000
    assert omega.effective_ns==99_980_000_000 and v.effective_ns==99_970_000_000
    assert angle.received_ns==100_030_000_000 and angle.value==.2 and x.value==.1
    assert provider.last_timing['host_read_to_result_ms']==10.
    assert not any(key in snapshot for key in ('comparison','measurement_quality','video','camera','tracking'))
    now[0]=100.3
    stale=client.get('/api/state?measurement=1').json
    assert stale['stale'] and stale['theta_rad'] is None and stale['omega_effective_t'] is None
    assert stale['t']==100. and stale['calibration']==snapshot['calibration']
    # A fresh provider is only to convert this same stale frame; repeated-frame
    # rejection is independently covered by the existing VisionProvider tests.
    provider=VisionProvider(Session('measurement-test','host'),frame_id='explicit-camera-frame',
        clock_mapping=ClockMapping('camera-host','host',0),calibration=stale['calibration'])
    observation=provider.observation(stale,received_ns=100_300_000_000,source_clock_id='camera-host')
    assert all(s.validity=='invalid' and s.value is None for s in observation.samples)
