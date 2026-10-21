"""Passive sweep analysis: frozen validation, monotonicity, and stationary gaps."""
from pathlib import Path
import importlib.util
import numpy as np


def module():
    spec=importlib.util.spec_from_file_location('manual_map',Path(__file__).with_name('analyze_manual_map.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def test_periodic_map_fits_only_training_direction_and_checks_monotonicity():
    m=module();q=np.linspace(-np.pi,np.pi,200,endpoint=False)
    def rows(offset):return [dict(encoder_rad=float(x),residual_rad=float(.02+.1*np.sin(x)+offset)) for x in q]
    result=m.fit_periodic_models(rows(0),rows(.05))
    model=result['periodic_order2']
    assert abs(model['coefficients'][1]-.1)<1e-10
    assert model['train']['rms_deg']<1e-8
    assert abs(model['opposite_direction']['rms_deg']-np.degrees(.05))<1e-8
    assert abs(model['minimum_derivative']-.9)<1e-6
    assert model['mathematically_monotonic'] is True


def test_nonmonotonic_periodic_candidate_is_not_marked_monotonic():
    m=module();q=np.linspace(-np.pi,np.pi,100,endpoint=False)
    rows=[dict(encoder_rad=float(x),residual_rad=float(2*np.sin(x))) for x in q]
    r=m.fit_periodic_models(rows,rows)['periodic_order2']
    assert r['mathematically_monotonic'] is False
    assert r['minimum_derivative']<0


def test_quiet_hold_does_not_bridge_telemetry_gap():
    m=module();t=np.r_[np.arange(0,.5,.004),np.arange(.8,1.3,.004)]
    assert m.quiet_intervals(t,np.zeros(len(t)),np.zeros(len(t)),min_duration=.6)==[]
    t=np.arange(0,1,.004)
    result=m.quiet_intervals(t,np.zeros(len(t)),np.zeros(len(t)),min_duration=.6)
    assert len(result)==1 and result[0]['encoder_stationary_qualified']


def test_approach_label_requires_substantial_motion_not_upright_jitter():
    m=module();t=np.arange(0,3,.004)
    assert m.approach_direction(t,.005*np.sin(12*t),2.5,before=True)==0
    assert m.approach_direction(t,.2*t,2.5,before=True)==1
    assert m.approach_direction(t,-.2*t,.2,before=False)==-1
