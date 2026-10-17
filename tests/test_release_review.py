"""Offline release evidence must come from raw geometry and measured hanging zero."""
import gzip
import hashlib
import json
import math
from pathlib import Path

import pytest


def _write(path, value):
    path.write_text(json.dumps(value))


def _rows(path, rows):
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows))


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recording(tmp_path):
    raw = tmp_path / 'rig-test.jsonl'
    annotations = tmp_path / 'annotations.json'
    camera = tmp_path / 'vision.ndjson'
    baseline = dict(schema='cartpole-passive-baseline-v1', duration_s=2.,
        window_host_ns=[10_000_000_000, 12_000_000_000],
        zeroing='experiment-relative only; raw readings and saved upright unchanged',
        encoder=dict(raw_angle_rad=math.pi-.09, spread_rad=.001, sample_count=200),
        camera=dict(image_angle_rad=1.6, spread_rad=.001, sample_count=100,
                    length_px=100., pivot_px=[250.,250.], frame_width=640, frame_height=480, rotation=0))
    rows = [dict(type='session', session=dict(session_id='7',clock_id='board:7')),
            dict(type='info', info=dict(sid=7,firmware='executor-v6-measuredrail',encoder_upright_raw=100,
                 home_epoch=2,reference_saved=True,encoder_conf_valid=True)),
            dict(type='passive_start',seconds=4.5), dict(type='passive_baseline',baseline=baseline)]
    def excursion(t):
        if t <= 2.: return 0.
        if t < 2.1: return 4*(t-2.)
        if t <= 2.4: return .4
        return .4*math.cos(6*(t-2.4))*math.exp(-.4*(t-2.4))
    for tick in range(451):
        t = tick/100
        rows.append(dict(type='state',state=dict(sid=7,unwrapped_us=tick*10000,unwrapped_tick=tick*10,
            received_ns=10_000_000_000+tick*10_000_000,theta=math.pi-.09+excursion(t),
            flags=205,fault=0,mode=0)))
    _rows(raw, rows)
    frames=[]
    for seq in range(226):
        t=seq/50; a=1.6-excursion(t)
        frames.append(dict(schema='cartpole-sensing-stream-v1',stream_seq=seq,host_t=100+t+.001,
            collector_received_ns=10_000_000_000+round(t*1e9)+2_000_000,
            encoder=dict(theta_rad=88.),fusion=dict(theta_rad=77.),
            vision=dict(seq=seq,t=100+t,detected=True,stale=False,confidence=.9,worker_error=None,
                image_angle_rad=a,theta_rad=99.,theta_down_rad=99.,pivot_px=[250.,250.],
                bob_px=[250+100*math.sin(a),250+100*math.cos(a)],length_px=100.,
                frame_width=640,frame_height=480)))
    _rows(camera,frames)
    def anchor(local):
        return dict(offset_ns=-90_000_000_000,uncertainty_ns=1_000_000,
            local_before_ns=local-1_000_000,local_after_ns=local+1_000_000,
            server_monotonic_s=local/1e9+90)
    vr=dict(sha256=_hash(camera),clock_sync=dict(method='http-roundtrip-midpoint',start=anchor(9_000_000_000),end=anchor(16_000_000_000)))
    _write(tmp_path/'vision-report.json',vr)
    _write(tmp_path/'report.json',dict(schema='cartpole-id-run-v1',raw_log=raw.name,raw_log_sha256=_hash(raw),
        completed=True,stop_confirmed=True,records_dropped=0,result=dict(baseline=baseline),camera=vr))
    _write(annotations,dict(schema='cartpole-passive-annotations-v1',source_sha256=_hash(raw),selected_before_scoring=True,
        operator_cart_restraint='held cart fixed',selection_method='independent hand-clear observation',
        episodes=[dict(episode_id='release-1',board_relative_s=[2.5,4.3],pose_board_relative_s=[2.1,2.4],
                      release_board_s=2.4,reason='hand clear')]))
    return raw,annotations


def bind_camera_report(tmp_path, report):
    _write(tmp_path/'vision-report.json',report)
    path=tmp_path/'report.json';completion=json.loads(path.read_text())
    completion['camera']=report;_write(path,completion)


def review(raw,annotations,out):
    from cartpole_sdk.identification.release_review import review_releases
    return review_releases(raw,annotations,out)


def change_camera(tmp_path,change):
    path=tmp_path/'vision.ndjson'; rows=[json.loads(x) for x in path.read_text().splitlines()]
    change(rows);_rows(path,rows)
    for name in ('vision-report.json','report.json'):
        target=tmp_path/name; report=json.loads(target.read_text())
        (report if name=='vision-report.json' else report['camera'])['sha256']=_hash(path)
        _write(target,report)


def test_raw_relative_camera_sign_pose_and_immutable_hashed_artifacts(tmp_path):
    raw,ann=recording(tmp_path); original=raw.read_bytes();out=tmp_path/'review'
    result=review(raw,ann,out);ep=result['episodes'][0]
    assert result['passed'] and ep['passed']
    assert result['camera_sign']==-1 and result['camera_scale']==1.
    assert ep['angular_rmse_rad']<.001 and ep['angular_p95_rad']<.001
    assert ep['camera_coverage_fraction']>.98 and ep['max_camera_gap_s']<.021
    pose=ep['release_pose']
    assert pose['verified'] and pose['encoder_median_rad']==pytest.approx(.4,abs=.0001)
    assert pose['camera_median_rad']==pytest.approx(.4,abs=.0001)
    assert ep['recorded_start_excursion_rad']==pytest.approx(.31718597254,abs=.001)
    assert result['source_sha256']==_hash(raw) and result['annotations_sha256']==_hash(ann)
    assert result['camera_sha256']==_hash(tmp_path/'vision.ndjson')
    assert result['absolute_angle_calibration'] is False and result['model_accepted'] is False
    assert ep['pivot_motion']['metric_stationarity_established'] is False
    assert json.loads((out/'report.json').read_text())==result
    assert (out/'release-overlay.png').stat().st_size>1000
    assert raw.read_bytes()==original
    with pytest.raises(FileExistsError): review(raw,ann,out)


def test_no_annotated_pose_never_labels_a_later_peak_as_release_angle(tmp_path):
    raw,ann=recording(tmp_path);a=json.loads(ann.read_text());a['episodes'][0].pop('pose_board_relative_s');_write(ann,a)
    pose=review(raw,ann,tmp_path/'review')['episodes'][0]['release_pose']
    assert not pose['verified'] and pose['encoder_median_rad'] is None and pose['camera_median_rad'] is None


@pytest.mark.parametrize('bad',('short','after_free','nonfinite','bad_release'))
def test_invalid_release_pose_annotation_rejected(tmp_path,bad):
    raw,ann=recording(tmp_path);a=json.loads(ann.read_text());ep=a['episodes'][0]
    if bad=='short':ep['pose_board_relative_s']=[2.3,2.4]
    elif bad=='after_free':ep['pose_board_relative_s']=[2.6,2.9]
    elif bad=='nonfinite':ep['pose_board_relative_s']=[float('nan'),2.4]
    else:ep['release_board_s']=2.2
    _write(ann,a)
    with pytest.raises(ValueError): review(raw,ann,tmp_path/'review')


def test_missing_camera_coverage_stays_missing_and_fails_gates(tmp_path):
    raw,ann=recording(tmp_path)
    change_camera(tmp_path,lambda rows:rows.__setitem__(slice(None),[r for r in rows if not 102.8<r['vision']['t']<103.6]))
    result=review(raw,ann,tmp_path/'review');ep=result['episodes'][0]
    assert not result['passed'] and not ep['passed']
    assert ep['max_camera_gap_s']>.7 and ep['camera_coverage_fraction']<.7
    assert ep['missing_camera_intervals_board_s']


def test_mirrored_theta_cannot_mask_raw_camera_disagreement(tmp_path):
    raw,ann=recording(tmp_path)
    def change(rows):
        for r in rows:
            if r['vision']['t']>=102.5:r['vision']['image_angle_rad']+=.3
    change_camera(tmp_path,change)
    ep=review(raw,ann,tmp_path/'review')['episodes'][0]
    assert not ep['passed']


@pytest.mark.parametrize('field,value',(('detected',False),('stale',True),('confidence',.49),('worker_error','failed'),('pivot_px',None),('bob_px',None),('length_px',0)))
def test_unusable_geometry_cannot_be_rescued_by_fused_angles(tmp_path,field,value):
    raw,ann=recording(tmp_path)
    change_camera(tmp_path,lambda rows:[r['vision'].__setitem__(field,value) for r in rows])
    ep=review(raw,ann,tmp_path/'review')['episodes'][0]
    assert not ep['passed'] and ep['valid_camera_frames']==0 and ep['angular_rmse_rad'] is None


@pytest.mark.parametrize('target',('vision','completion'))
def test_camera_tampering_is_rejected_by_both_bindings(tmp_path,target):
    raw,ann=recording(tmp_path)
    if target=='vision':
        with (tmp_path/'vision.ndjson').open('a') as stream:stream.write('{}\n')
    else:
        p=tmp_path/'report.json';v=json.loads(p.read_text());v['camera']['sha256']='0'*64;_write(p,v)
    with pytest.raises(ValueError,match='hash'): review(raw,ann,tmp_path/'review')


@pytest.mark.parametrize('bad',('missing','uncertain','incoherent','drift'))
def test_cross_host_clock_mapping_must_be_bounded_and_coherent(tmp_path,bad):
    raw,ann=recording(tmp_path);p=tmp_path/'vision-report.json';v=json.loads(p.read_text())
    if bad=='missing':v.pop('clock_sync')
    elif bad=='uncertain':v['clock_sync']['start']['uncertainty_ns']=11_000_000
    elif bad=='incoherent':v['clock_sync']['start']['offset_ns']+=5_000_000
    else:
        anchor=v['clock_sync']['end'];anchor['offset_ns']+=50_000_000;anchor['server_monotonic_s']-=.05
    bind_camera_report(tmp_path,v)
    with pytest.raises(ValueError,match='clock|sync|drift'): review(raw,ann,tmp_path/'review')


def test_gzip_rig_log_keeps_decompressed_hash_and_camera_siblings(tmp_path):
    raw,ann=recording(tmp_path);pin=_hash(raw);compressed=raw.with_suffix('.jsonl.gz');compressed.write_bytes(gzip.compress(raw.read_bytes()))
    result=review(compressed,ann,tmp_path/'review')
    assert result['passed'] and result['source_sha256']==pin


def test_camera_reader_honors_byte_bounds_before_parsing(tmp_path,monkeypatch):
    raw,ann=recording(tmp_path)
    from cartpole_sdk.identification import release_review
    monkeypatch.setattr(release_review,'MAX_CAMERA_BYTES',10)
    with pytest.raises(ValueError,match='byte limit'):review(raw,ann,tmp_path/'review')


def analyze(raw, annotations):
    from cartpole_sdk.identification.release_review import analyze_releases
    return analyze_releases(raw, annotations)


def change_raw(raw, annotations, change):
    rows=[json.loads(line) for line in raw.read_text().splitlines()];change(rows);_rows(raw,rows)
    p=raw.parent/'report.json';report=json.loads(p.read_text());report['raw_log_sha256']=_hash(raw);_write(p,report)
    annotation=json.loads(annotations.read_text());annotation['source_sha256']=_hash(raw);_write(annotations,annotation)


def test_pure_analysis_writes_no_artifacts(tmp_path):
    raw,ann=recording(tmp_path);before={p.name:p.read_bytes() for p in tmp_path.iterdir()}
    result=analyze(raw,ann)
    assert result['passed'] and result['all_release_poses_verified']
    assert {p.name:p.read_bytes() for p in tmp_path.iterdir()}==before


def test_geometry_consistent_camera_disagreement_measures_raw_error(tmp_path):
    raw,ann=recording(tmp_path)
    def change(rows):
        for r in rows:
            v=r['vision']
            if v['t']>=102.5:
                v['image_angle_rad']+=.3;a=v['image_angle_rad']
                v['bob_px']=[250+100*math.sin(a),250+100*math.cos(a)]
    change_camera(tmp_path,change)
    ep=analyze(raw,ann)['episodes'][0]
    assert not ep['passed'] and ep['valid_camera_frames']>80
    assert ep['angular_rmse_rad']==pytest.approx(.3,abs=.001)
    assert ep['angular_p95_rad']==pytest.approx(.3,abs=.001)


def test_agreeing_but_moving_held_pose_is_not_verified(tmp_path):
    raw,ann=recording(tmp_path)
    def move(rows):
        for r in rows:
            if r.get('type')=='state' and 2.1<=r['state']['unwrapped_us']/1e6<=2.4:
                r['state']['theta']+=2*(r['state']['unwrapped_us']/1e6-2.1)
    change_raw(raw,ann,move)
    def camera(rows):
        for r in rows:
            v=r['vision'];t=v['t']-100
            if 2.1<=t<=2.4:
                v['image_angle_rad']-=2*(t-2.1);a=v['image_angle_rad']
                v['bob_px']=[250+100*math.sin(a),250+100*math.cos(a)]
    change_camera(tmp_path,camera)
    result=analyze(raw,ann);pose=result['episodes'][0]['release_pose']
    assert result['passed'] and not result['all_release_poses_verified']
    assert not pose['verified'] and pose['encoder_spread_rad']>.2


def test_heartbeat_duplicates_do_not_inflate_unique_frame_evidence(tmp_path):
    raw,ann=recording(tmp_path)
    def duplicate(rows):
        doubled=[]
        for r in rows:
            doubled.append(r);copy=json.loads(json.dumps(r));copy['collector_received_ns']+=1_000_000;doubled.append(copy)
        for i,r in enumerate(doubled):r['stream_seq']=i
        rows[:]=doubled
    change_camera(tmp_path,duplicate)
    result=analyze(raw,ann)
    assert result['passed'] and result['duplicate_camera_frames']==226 and result['unique_camera_frames']==226


def test_contradictory_duplicate_raw_camera_frame_rejected(tmp_path):
    raw,ann=recording(tmp_path)
    def duplicate(rows):
        copy=json.loads(json.dumps(rows[140]));copy['vision']['image_angle_rad']+=.3
        copy['collector_received_ns']+=1_000_000;rows.insert(141,copy)
        for i,r in enumerate(rows):r['stream_seq']=i
    change_camera(tmp_path,duplicate)
    with pytest.raises(ValueError,match='contradictory'):analyze(raw,ann)


def test_camera_receipt_clock_reversal_rejected(tmp_path):
    raw,ann=recording(tmp_path)
    def reverse(rows):rows[140]['collector_received_ns']=rows[141]['collector_received_ns']+1
    change_camera(tmp_path,reverse)
    with pytest.raises(ValueError,match='receipt'):analyze(raw,ann)


@pytest.mark.parametrize('limit',('MAX_CAMERA_RECORDS','MAX_METADATA_BYTES'))
def test_record_and_metadata_bounds_fail_before_unbounded_read(tmp_path,monkeypatch,limit):
    raw,ann=recording(tmp_path)
    from cartpole_sdk.identification import release_review
    monkeypatch.setattr(release_review,limit,3)
    with pytest.raises(ValueError,match='limit'):analyze(raw,ann)


def test_baseline_must_precede_release_pose_and_free_interval(tmp_path):
    raw,ann=recording(tmp_path)
    def change(rows):
        for row in rows:
            if row.get('type')=='passive_baseline':row['baseline']['window_host_ns']=[12_200_000_000,14_200_000_000]
    change_raw(raw,ann,change)
    p=tmp_path/'report.json';r=json.loads(p.read_text());r['result']['baseline']['window_host_ns']=[12_200_000_000,14_200_000_000];_write(p,r)
    with pytest.raises(ValueError,match='baseline'):analyze(raw,ann)


def test_fewer_than_ten_frames_cannot_pass_even_when_all_geometry_agrees(tmp_path):
    raw,ann=recording(tmp_path);a=json.loads(ann.read_text());a['episodes'][0]['board_relative_s']=[2.5,2.65];_write(ann,a)
    ep=analyze(raw,ann)['episodes'][0]
    assert not ep['passed'] and ep['valid_camera_frames']==8


def test_linear_anchor_offset_interpolation_is_used_without_fitting_angles(tmp_path):
    raw,ann=recording(tmp_path)
    # Local time at remote 99 is 9; at remote 106 is 16.001.
    p=tmp_path/'vision-report.json';r=json.loads(p.read_text());end=r['clock_sync']['end']
    end['offset_ns']+=1_000_000;end['local_before_ns']+=1_000_000;end['local_after_ns']+=1_000_000;bind_camera_report(tmp_path,r)
    def camera(rows):
        for r in rows:
            v=r['vision'];server=v['t'];local_t=(server-100)+(server-99)/7000
            r['collector_received_ns']=10_000_000_000+round(local_t*1e9)+2_000_000
            if local_t>2.4:
                excursion=.4*math.cos(6*(local_t-2.4))*math.exp(-.4*(local_t-2.4))
                a=1.6-excursion;v['image_angle_rad']=a;v['bob_px']=[250+100*math.sin(a),250+100*math.cos(a)]
    change_camera(tmp_path,camera)
    result=analyze(raw,ann);ep=result['episodes'][0]
    assert result['passed'] and ep['angular_rmse_rad']<.00003


def _prepend_camera_frame(tmp_path, source_t):
    def prepend(rows):
        first=json.loads(json.dumps(rows[0]));first['vision']['t']=source_t
        first['collector_received_ns']=9_005_000_000;first['host_t']=99.005
        rows.insert(0,first)
        for i,row in enumerate(rows):row['stream_seq']=i;row['vision']['seq']=i
    change_camera(tmp_path,prepend)


def test_short_camera_preroll_is_preserved_unmapped_and_excluded_from_comparison(tmp_path):
    raw,ann=recording(tmp_path)
    _prepend_camera_frame(tmp_path,98.85)
    result=analyze(raw,ann)
    assert result['passed'] and result['all_release_poses_verified']
    assert result['camera_preroll']==dict(frames=1,source_time_bounds_s=[98.85,98.85],
        mapped=False,comparison_included=False,max_allowed_before_start_s=.15)
    assert result['unique_camera_frames']==227
    assert result['episodes'][0]['valid_camera_frames']==91


@pytest.mark.parametrize('source_t', (98.849,106.001))
def test_camera_preroll_does_not_permit_substantive_or_future_clock_extrapolation(tmp_path,source_t):
    raw,ann=recording(tmp_path)
    if source_t<99:
        _prepend_camera_frame(tmp_path,source_t)
    else:
        def append(rows):
            last=json.loads(json.dumps(rows[-1]));last['vision']['t']=source_t
            last['collector_received_ns']=16_002_000_000;last['stream_seq']+=1;last['vision']['seq']+=1;rows.append(last)
        change_camera(tmp_path,append)
    with pytest.raises(ValueError,match='anchor coverage'):analyze(raw,ann)


def test_preroll_still_rejects_reversed_source_time(tmp_path):
    raw,ann=recording(tmp_path)
    _prepend_camera_frame(tmp_path,98.9)
    def reverse(rows):
        row=json.loads(json.dumps(rows[0]));row['vision']['t']=98.89;row['collector_received_ns']+=1_000_000
        rows.insert(1,row)
        for i,row in enumerate(rows):row['stream_seq']=i;row['vision']['seq']=i
    change_camera(tmp_path,reverse)
    with pytest.raises(ValueError,match='reversed'):analyze(raw,ann)


@pytest.mark.parametrize('length,expected_valid', ((79.9,False),(80.,True),(120.,True),(120.1,False)))
def test_camera_marker_length_must_remain_within_twenty_percent_of_baseline(tmp_path,length,expected_valid):
    raw,ann=recording(tmp_path)
    def resize(rows):
        for r in rows:
            v=r['vision']
            if v['t']>=102.5:
                v['length_px']=length;a=v['image_angle_rad'];v['bob_px']=[250+length*math.sin(a),250+length*math.cos(a)]
    change_camera(tmp_path,resize)
    ep=analyze(raw,ann)['episodes'][0]
    assert ep['passed'] is expected_valid
    assert ep['valid_camera_frames']==(91 if expected_valid else 0)


def test_held_pose_without_explicit_release_time_reports_values_but_is_not_verified(tmp_path):
    raw,ann=recording(tmp_path);a=json.loads(ann.read_text());a['episodes'][0].pop('release_board_s');_write(ann,a)
    result=analyze(raw,ann);pose=result['episodes'][0]['release_pose']
    assert result['passed'] and not result['all_release_poses_verified']
    assert not pose['verified'] and pose['encoder_median_rad']==pytest.approx(.4)
    assert pose['camera_median_rad']==pytest.approx(.4) and pose['release_board_s'] is None
    assert 'explicit release time' in ' '.join(pose['reasons'])


@pytest.mark.parametrize('release,expected_verified', ((2.9,True),(2.901,False)))
def test_old_held_pose_cannot_verify_later_release_and_free_interval_gap_is_explicit(tmp_path,release,expected_verified):
    raw,ann=recording(tmp_path);a=json.loads(ann.read_text());ep=a['episodes'][0]
    ep['release_board_s']=release;ep['board_relative_s']=[3.5,4.3];_write(ann,a)
    pose=analyze(raw,ann)['episodes'][0]['release_pose']
    assert pose['verified'] is expected_verified
    assert pose['pose_to_release_gap_s']==pytest.approx(release-2.4)
    assert pose['release_to_free_gap_s']==pytest.approx(3.5-release)
    assert pose['handling_independently_verified'] is False
    assert 'handling' in pose['timing_note'].lower()


@pytest.mark.parametrize('baseline_length,amplitude,expected_pass,threshold',
                         ((100.,4.,True,4.),(100.,6.,False,4.),(300.,5.,True,6.),(300.,8.,False,6.)))
def test_pivot_motion_screen_uses_pixel_floor_and_baseline_length(tmp_path,baseline_length,amplitude,expected_pass,threshold):
    raw,ann=recording(tmp_path)
    def baseline(rows):
        for row in rows:
            if row.get('type')=='passive_baseline':row['baseline']['camera']['length_px']=baseline_length
    change_raw(raw,ann,baseline)
    p=tmp_path/'report.json';r=json.loads(p.read_text());r['result']['baseline']['camera']['length_px']=baseline_length;_write(p,r)
    def motion(rows):
        for row in rows:
            v=row['vision'];a=v['image_angle_rad'];x=250.
            if 102.5<=v['t']<=104.3:x+=amplitude*math.sin(2*math.pi*(v['t']-102.5)/1.8)
            v['pivot_px']=[x,250.];v['length_px']=baseline_length
            v['bob_px']=[x+baseline_length*math.sin(a),250+baseline_length*math.cos(a)]
    change_camera(tmp_path,motion)
    result=analyze(raw,ann);ep=result['episodes'][0];pivot=ep['pivot_motion']
    assert result['passed'] is expected_pass and ep['passed'] is expected_pass
    assert pivot['provisional_fixed_pivot_screen_passed'] is expected_pass
    assert pivot['radial_p95_limit_px']==threshold
    assert pivot['metric_stationarity_established'] is False
    assert ep['angular_rmse_rad']<.001


def test_coherent_camera_clock_change_must_match_completion_report(tmp_path):
    raw,ann=recording(tmp_path);path=tmp_path/'vision-report.json';report=json.loads(path.read_text())
    # A coherent 5 ms earlier mapping passes the drift and receipt checks but
    # must not replace the clock evidence preserved by collection completion.
    for anchor in report['clock_sync']['start'],report['clock_sync']['end']:
        for key in ('offset_ns','local_before_ns','local_after_ns'):anchor[key]-=5_000_000
    _write(path,report)
    with pytest.raises(ValueError,match='camera report.*completion'):
        analyze(raw,ann)
