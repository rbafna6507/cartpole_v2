"""Passive zeroing must use quiet, independent raw encoder and camera readings."""
from copy import deepcopy
import math

import pytest

from cartpole_sdk.contracts import ValidationError


def encoder_states(count=501, duration=2.0, angle=math.pi-math.pi/30):
    return [dict(theta=angle, received_ns=1_000_000_000+round(i*duration*1e9/(count-1)),
                 unwrapped_us=5_000_000+round(i*duration*1e6/(count-1)),
                 mode=0, flags=205, fault=0, angle_hat=0.0, omega=123.0)
            for i in range(count)]


def camera_rows(count=61, duration=2.0, angle=-math.pi/30):
    rows=[]
    for i in range(count):
        t=100+i*duration/(count-1)
        rows.append(dict(schema='cartpole-sensing-stream-v1',stream_seq=i,
            collector_received_ns=1_000_000_000+round(i*duration*1e9/(count-1)),host_t=t+.01,
            vision=dict(seq=i,t=t,detected=True,stale=False,worker_error=None,
                confidence=.9,image_angle_rad=angle,pivot_px=[320.,180.],
                bob_px=[320+100*math.sin(angle),180+100*math.cos(angle)],length_px=100.,
                frame_width=640,frame_height=480,camera={'rotation':0},
                theta_rad=2.,theta_down_rad=2.,omega_rad_s=123.,angle_valid=False)))
    return rows


def build(states=None, rows=None, **kwargs):
    from cartpole_sdk.identification.passive_baseline import build_baseline
    return build_baseline(encoder_states() if states is None else states,
                          camera_rows() if rows is None else rows,**kwargs)


def test_nonzero_hanging_measurement_is_the_baseline_and_inputs_are_unchanged():
    states=encoder_states();rows=camera_rows();before=deepcopy((states,rows))
    result=build(states,rows)
    assert result['schema']=='cartpole-passive-baseline-v1'
    assert result['encoder']['raw_angle_rad']==pytest.approx(3.036872898470133)
    assert result['camera']['image_angle_rad']==pytest.approx(-.10471975511965977)
    assert result['encoder']['spread_rad']==pytest.approx(0.)
    assert result['encoder']['sample_count']==501
    assert result['encoder']['first_host_ns']==1_000_000_000
    assert result['encoder']['last_host_ns']==3_000_000_000
    assert result['encoder']['first_board_us']==5_000_000
    assert result['encoder']['last_board_us']==7_000_000
    assert result['camera']['sample_count']==61
    assert result['camera']['length_px']==pytest.approx(100.)
    assert result['camera']['pivot_px']==[320.,180.]
    assert result['camera']['frame_width']==640
    assert result['camera']['frame_height']==480
    assert result['camera']['rotation']==0
    assert result['window_host_ns']==[1_000_000_000,3_000_000_000]
    assert result['duration_s']==pytest.approx(2.)
    assert 'experiment-relative only' in result['zeroing']
    assert 'saved upright unchanged' in result['zeroing']
    assert (states,rows)==before


def test_circular_medians_handle_pi_wrap_without_false_motion():
    states=encoder_states();rows=camera_rows(angle=math.pi)
    for i,state in enumerate(states):state['theta']=math.pi-.004 if i%2 else -math.pi+.004
    for i,row in enumerate(rows):
        angle=math.pi-.004 if i%2 else -math.pi+.004
        row['vision'].update(image_angle_rad=angle,
            bob_px=[320+100*math.sin(angle),180+100*math.cos(angle)])
    result=build(states,rows)
    assert abs(abs(result['encoder']['raw_angle_rad'])-math.pi)<.005
    assert abs(abs(result['camera']['image_angle_rad'])-math.pi)<.005
    assert result['encoder']['spread_rad']==pytest.approx(.008)
    assert result['camera']['spread_rad']==pytest.approx(.008)


@pytest.mark.parametrize('change',[
    {'detected':False},{'stale':True},{'worker_error':'lost camera'},
    {'confidence':.49},{'confidence':float('nan')},{'image_angle_rad':None},
    {'image_angle_rad':float('inf')},{'pivot_px':[1.,float('nan')]},
    {'bob_px':[1.]},{'length_px':5.},{'length_px':120.},
    {'image_angle_rad':.1},
])
def test_camera_geometry_rejects_invalid_raw_pose(change):
    from cartpole_sdk.identification.passive_baseline import camera_geometry
    vision=camera_rows()[0]['vision'];vision.update(change)
    assert camera_geometry(vision) is None


def test_camera_geometry_uses_raw_pose_and_ignores_filtered_and_mirror_values():
    from cartpole_sdk.identification.passive_baseline import camera_geometry
    vision=camera_rows()[0]['vision']
    vision.update(theta_rad=float('nan'),theta_down_rad=None,angle_valid=False,
                  fused={'theta_rad':99},comparison={'theta_rad':88},mirror={'theta_rad':77})
    result=camera_geometry(vision)
    assert result['image_angle_rad']==pytest.approx(-.10471975511965977)
    assert result['pivot_px']==[320.,180.]
    assert result['bob_px']==vision['bob_px']


@pytest.mark.parametrize('change',[
    {'theta':0.},{'theta':float('nan')},{'flags':207},{'flags':204},
    {'fault':1},{'mode':12},{'enabled':True},{'healthy':False},
])
def test_invalid_or_unsafe_encoder_samples_fail_closed(change):
    states=encoder_states();states[250].update(change)
    with pytest.raises(ValidationError,match='hanging'):
        build(states)


@pytest.mark.parametrize('kind',['host_duration','board_duration','few_samples','host_reverse','board_reverse','duplicate'])
def test_encoder_window_requires_sustained_unique_ordered_samples(kind):
    states=encoder_states()
    if kind=='host_duration':
        for s in states:s['received_ns']=1_000_000_000+(s['received_ns']-1_000_000_000)//2
    elif kind=='board_duration':
        for s in states:s['unwrapped_us']=5_000_000+(s['unwrapped_us']-5_000_000)//2
    elif kind=='few_samples':states=encoder_states(count=99)
    elif kind=='host_reverse':states[250]['received_ns']=states[249]['received_ns']-1
    elif kind=='board_reverse':states[250]['unwrapped_us']=states[249]['unwrapped_us']-1
    else:states[250]=dict(states[249])
    with pytest.raises(ValidationError,match='hanging'):
        build(states)


def test_camera_is_required_even_when_encoder_is_quiet():
    with pytest.raises(ValidationError,match='markers'):
        build(rows=[])


@pytest.mark.parametrize('kind',['few_frames','poor_coverage','short_span','gap','angle_motion','length_motion','pivot_motion','resolution','rotation'])
def test_camera_window_rejects_inadequate_or_moving_geometry(kind):
    rows=camera_rows()
    if kind=='few_frames':rows=camera_rows(count=29)
    elif kind=='poor_coverage':
        for r in rows[::4]:r['vision']['detected']=False
    elif kind=='short_span':rows=camera_rows(duration=1.4)
    elif kind=='gap':del rows[20:30]
    elif kind=='angle_motion':
        for r in rows[30:]:
            a=.1;r['vision'].update(image_angle_rad=a,bob_px=[320+100*math.sin(a),180+100*math.cos(a)])
    elif kind=='length_motion':
        for r in rows[30:]:
            v=r['vision'];v['length_px']=120.;v['bob_px']=[320+120*math.sin(v['image_angle_rad']),180+120*math.cos(v['image_angle_rad'])]
    elif kind=='pivot_motion':
        for r in rows[30:]:r['vision']['pivot_px'][0]+=10;r['vision']['bob_px'][0]+=10
    elif kind=='resolution':rows[-1]['vision']['frame_width']=1280
    else:rows[-1]['vision']['camera']['rotation']=90
    with pytest.raises(ValidationError,match='markers|camera fixed'):
        build(rows=rows)


def test_fresh_duplicate_source_frame_heartbeats_do_not_inflate_valid_sample_count():
    rows=camera_rows();duplicate=deepcopy(rows[25]);duplicate['collector_received_ns']+=1
    duplicate['stream_seq']+=.5;rows.insert(26,duplicate)
    result=build(rows=rows)
    assert result['camera']['sample_count']==61


@pytest.mark.parametrize('kind',['seq_reverse','time_reverse','same_seq_new_time','same_time_new_seq','changed_duplicate','receipt_reverse','nonfinite_receipt'])
def test_camera_identity_and_local_receipt_cannot_be_contradictory(kind):
    rows=camera_rows()
    if kind=='seq_reverse':rows[25]['vision']['seq']=23
    elif kind=='time_reverse':rows[25]['vision']['t']=rows[24]['vision']['t']-.01
    elif kind=='same_seq_new_time':rows[25]['vision']['seq']=24
    elif kind=='same_time_new_seq':rows[25]['vision']['t']=rows[24]['vision']['t']
    elif kind=='changed_duplicate':
        rows[25]['vision'].update(seq=24,t=rows[24]['vision']['t'],confidence=.7)
    elif kind=='receipt_reverse':rows[25]['collector_received_ns']=rows[24]['collector_received_ns']-1
    else:rows[25]['collector_received_ns']=float('nan')
    with pytest.raises(ValidationError,match='markers|camera fixed'):
        build(rows=rows)


def test_camera_frames_outside_encoder_host_window_do_not_count():
    rows=camera_rows()
    for r in rows:r['collector_received_ns']+=2_000_000_001
    with pytest.raises(ValidationError,match='markers'):
        build(rows=rows)


def test_sparse_encoder_motion_cannot_hide_inside_percentile_spread():
    states=encoder_states();states[200]['theta']+=.031
    with pytest.raises(ValidationError,match='raw encoder angle moved'):
        build(states)


def test_camera_missing_raw_geometry_cannot_fall_back_to_filtered_fields():
    rows=camera_rows()
    for row in rows:
        row['vision'].pop('image_angle_rad')
        row['vision']['theta_rad']=0.
    with pytest.raises(ValidationError,match='markers'):
        build(rows=rows)


def test_missing_rotation_remains_unknown_instead_of_becoming_zero():
    rows=camera_rows()
    for row in rows:row['vision'].pop('camera')
    assert build(rows=rows)['camera']['rotation'] is None


def test_camera_state_rotation_is_read_from_nested_capture_settings():
    rows=camera_rows()
    for row in rows:row['vision']['camera']={'settings':{'rotation':90}}
    assert build(rows=rows)['camera']['rotation']==90


def test_disagreeing_rotation_metadata_is_rejected():
    rows=camera_rows()
    for row in rows:
        row['vision']['camera']={'settings':{'rotation':90}}
        row['vision']['rotation']=0
    with pytest.raises(ValidationError,match='rotation'):
        build(rows=rows)


def test_exactly_eighty_percent_valid_frames_are_sufficient_with_continuity():
    rows=camera_rows(count=60)
    for row in rows[2::5]:row['vision']['detected']=False
    result=build(rows=rows)
    assert result['camera']['sample_count']==48
    assert result['camera']['valid_fraction']==pytest.approx(.8)


@pytest.mark.parametrize('duration',[0.,-1.,float('nan'),float('inf'),True])
def test_baseline_duration_must_be_finite_positive_real(duration):
    with pytest.raises(ValidationError,match='duration'):
        build(duration_s=duration)


@pytest.mark.parametrize('flags',[1,5,9,205|16,205|32,205|256])
def test_baseline_requires_home_switch_profile_and_no_limit_or_calibration_flags(flags):
    states=encoder_states();states[100]['flags']=flags
    with pytest.raises(ValidationError):build(states)
