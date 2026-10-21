"""Synthetic offline analysis regressions; no hardware or network access."""
import importlib.util
from pathlib import Path
import numpy as np

PATH=Path(__file__).with_name('analyze.py')
def module():
    spec=importlib.util.spec_from_file_location('tightening_analysis',PATH)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def test_circular_counts_cross_wrap_without_false_full_turn_spread():
    m=module();s=m.circular_summary([4095.,0.,1.],period=4096)
    assert abs(s['median'])<1e-8
    assert abs(s['span']-2.)<1e-8

def test_interpolation_rejects_long_gap_and_wraps_short_angle_arc():
    m=module()
    t=np.array([0.,.01,.06,.07]);values=np.array([3.13,-3.13,0.,.1])
    out,valid=m.interpolate(t,values,np.array([.005,.03,.065]),angular=True)
    assert valid.tolist()==[True,False,True]
    assert abs(abs(out[0])-np.pi)<1e-8
    assert np.isnan(out[1])

def test_lower_envelope_ignores_serial_receipt_bursts():
    m=module();b=np.arange(0,15,.004);h=100+b*1.00002+.0002
    h[::10]+=.06
    mapped,report=m.map_board_clock(b,h)
    assert np.max(np.abs(mapped-(100+b*1.00002+.0002)))<.0001
    assert report['receipt_delay_s']['p95']>.05

def test_duration_excludes_unknown_gap_and_separates_longest_hold():
    m=module();r=m.durations(np.array([0.,.01,.02,.10,.11,.12]),np.ones(6,dtype=bool))
    assert abs(r['total_s']-.04)<1e-9
    assert abs(r['longest_continuous_s']-.02)<1e-9

def test_differential_subtracts_observed_camera_pose_change():
    m=module()
    before={'state_reconstructed_counts':{'median':4094.},'camera_image_upright_rad':{'median':3.10},'native_info_counts_all':{'median':4094.}}
    after={'state_reconstructed_counts':{'median':3.},'camera_image_upright_rad':{'median':3.10+2*2*np.pi/4096},'native_info_counts_all':{'median':3.}}
    r=m.rest_difference(before,after)
    assert abs(r['state_shift_counts']-5)<1e-8
    assert abs(r['camera_change_equivalent_counts']-2)<1e-8
    assert abs(r['state_minus_camera_shift_counts']-3)<1e-8

def test_native_info_unchanged_count_duration_is_not_a_freshness_filter():
    m=module()
    trial={'reference':520,'events':[{'event':'initial_rest_start','host_monotonic_ns':0},{'event':'initial_rest_end','host_monotonic_ns':5_000_000_000}],
      'states':[{'received_ns':1_000_000_000,'theta':3.0,'omega':0.,'x':0.,'mode':0,'flags':205,'fault':0}],
      'camera':[{'t':1.,'angle':3.1,'pivot_x':0.,'length':150.}],
      'infos':[{'received_ns':1_000_000_000,'encoder_raw':2476,'encoder_raw_age_us':4_000_000}]}
    rest=m.rest_report(trial,'initial_rest')
    delta=m.rest_difference(rest,rest)
    assert delta['native_info_shift_counts']==0.
    assert rest['native_info_unchanged_duration_us']['median']==4_000_000

def test_paired_hold_segments_break_across_telemetry_dropout():
    m=module()
    ss=[dict(theta=0.,omega=0.,x=0.,velocity=0.,fault=0,flags=207,mode=3) for _ in range(4)]
    cc=[dict(t=t,angle=0.,segment=1,confidence=.9,length=150.,seq=i) for i,t in enumerate((.005,.065))]
    rows=m.paired({'camera':cc,'host':np.array([0.,.01,.06,.07]),'states':ss},0.)
    assert len(rows)==2
    assert rows[0]['segment']!=rows[1]['segment']

def test_synthetic_lag_recovers_known_delay_with_constant_angle_bias():
    m=module(); t=np.arange(0,6,.004)
    angle=lambda x:.8*np.sin(3*x)+.2*np.sin(7*x)
    rate=lambda x:2.4*np.cos(3*x)+1.4*np.cos(7*x)
    ss=[dict(theta=q,omega=w,x=0.,velocity=0.,fault=0,flags=207,mode=2) for q,w in zip(angle(t),rate(t))]
    cc=[dict(t=c,angle=float(angle(c-.023)+.12),segment=1,confidence=.9,length=150.,seq=i) for i,c in enumerate(np.arange(.2,5.8,.02))]
    result=m.fit_lag({'name':'synthetic','camera':cc,'host':t,'states':ss})
    assert abs(result['lag_s']+.023)<.00101
    assert result['frozen_for_later_trials'] is True

def test_rest_quality_does_not_accept_enabled_or_moving_board():
    m=module()
    trial={'reference':520,'events':[{'event':'initial_rest_start','host_monotonic_ns':0},{'event':'initial_rest_end','host_monotonic_ns':5_000_000_000}],
      'states':[{'received_ns':int(t*1e9),'theta':3.,'omega':.4,'x':0.,'mode':3,'flags':207,'fault':0} for t in np.linspace(0,5,126)],
      'camera':[],'infos':[]}
    result=m.rest_report(trial,'initial_rest')
    assert result['encoder_rest_qualified'] is False
    assert result['disabled_and_healthy'] is False
