import pytest
from cartpole_vision.state import StateEstimator
from .test_state import pose


@pytest.mark.parametrize('action',['home','a','b','reset'])
def test_calibration_never_relabels_previous_valid_measurement(action):
    estimator=StateEstimator()
    estimator.home_angle=.1;estimator.home_length=180
    estimator.cart_a=[200,100];estimator.cart_b=[400,100];estimator.cart_span_mm=400
    for seq in range(25):estimator.update(pose(.2,p=(300,100)),10+seq*.01)
    assert estimator.snapshot(10.24)['angle_valid']
    assert estimator.snapshot(10.24)['omega_rad_s'] is not None
    if action=='home':estimator.home()
    elif action=='reset':estimator.reset()
    else:estimator.mark_cart(action,400)
    result=estimator.snapshot(10.24)
    assert result['angle_valid'] is False and result['cart_valid'] is False
    for key in ('theta_rad','omega_rad_s','cart_x_m','cart_v_m_s','omega_effective_t','cart_velocity_effective_t'):
        assert result[key] is None
    assert result.get('t') is None
    if action!='reset':
        estimator.update(pose(.2,p=(300,100)),10.25)
        assert estimator.snapshot(10.25)['angle_valid']
