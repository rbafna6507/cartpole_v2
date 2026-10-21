"""Offline analysis regression: gaps, coordinate anchors and post-catch windows."""
import importlib.util
from pathlib import Path
import numpy as np


def module():
    path=Path(__file__).with_name('analyze_ref533.py')
    spec=importlib.util.spec_from_file_location('ref533_analysis',path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod


def test_window_metrics_preserve_position_drift_and_break_command_variation_at_gap():
    m=module()
    t=np.r_[np.arange(0,3,.004),np.arange(4,7,.004)]
    x=.01+.002*t
    command=np.where(t<3,1.,10.)
    result=m.signal_metrics(t,x)
    jitter=m.signal_metrics(t,command)
    assert abs(result['slope_per_s']-.002)<1e-10
    assert abs(result['mean']-float(np.mean(x)))<1e-10
    assert jitter['total_variation']==0
    assert jitter['gaps_over_30ms']==1


def test_continuous_balance_segment_stops_at_first_exit_and_ignores_later_recapture():
    m=module()
    t=np.arange(0,5,.004)
    modes=np.where((t>=1)&(t<3)|(t>=4),3,2)
    result=m.first_balance_run(t,modes)
    assert abs(result['first_s']-1)<1e-10
    assert abs(result['last_s']-2.996)<1e-10
    assert abs(result['duration_s']-1.996)<1e-10
    assert result['later_balance_samples']>0


def test_upward_anchor_is_converted_from_native_count_into_current_reference():
    m=module()
    anchor=dict(native_encoder_counts=dict(median=533),camera_image_angle_rad=dict(median=-.01))
    assert m.upright_encoder_angle(anchor,533)==0
    assert abs(m.upright_encoder_angle(anchor,520)-13*2*np.pi/4096)<1e-12


def test_upright_repeat_difference_uses_native_counts_across_changed_saved_reference():
    m=module()
    before=dict(native_encoder_counts=dict(median=533),camera_image_angle_rad=dict(median=-.01),
                reference_during_measurement=520,encoder_angle_rad=dict(median=13*2*np.pi/4096))
    after=dict(native_encoder_counts=dict(median=538),camera_image_angle_rad=dict(median=-.005),
               reference_during_measurement=533,encoder_angle_rad=dict(median=5*2*np.pi/4096))
    result=m.upright_repeat_difference(before,after)
    assert abs(result['native_shift_counts']-5)<1e-9
    assert abs(result['encoder_minus_camera_shift_deg']-np.degrees(5*2*np.pi/4096-.005))<1e-9
