"""Measured baseline and independent camera evidence must survive into fitting."""
import hashlib
import json
import math
from pathlib import Path
from unittest.mock import patch
import pytest
from test_release_review import recording, change_camera


def test_raw_review_uses_measured_hanging_zero_without_changing_raw(tmp_path):
    from cartpole_sdk.identification.review import review_recording
    raw,ann=recording(tmp_path);before=raw.read_bytes()
    result=review_recording(raw,tmp_path/'review')
    assert result['hanging_zero_measured'] is True
    assert result['plot_zero_rad']==pytest.approx(3.141592653589793-.09)
    assert raw.read_bytes()==before


def test_missing_or_mismatched_new_baseline_cannot_fall_back_to_pi(tmp_path):
    from cartpole_sdk.identification.workflow import load_records
    raw,ann=recording(tmp_path)
    rows=[json.loads(x) for x in raw.read_text().splitlines()]
    for row in rows:
        if row['type']=='passive_start':row.update(measurement_version=2,baseline_sha256='0'*64)
    raw.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    p=tmp_path/'report.json';report=json.loads(p.read_text());report['raw_log_sha256']=hashlib.sha256(raw.read_bytes()).hexdigest();p.write_text(json.dumps(report))
    with pytest.raises(ValueError,match='baseline'):load_records(raw)


def test_template_requires_pose_for_new_camera_backed_recording(tmp_path):
    from cartpole_sdk.identification.workflow import annotation_template
    raw,ann=recording(tmp_path);value=annotation_template(raw)
    assert value['release_pose_required'] is True
    assert value['measured_baseline']['schema']=='cartpole-passive-baseline-v1'
    assert 'pose_board_relative_s' in value['instructions']
    assert value['episodes']==[] and value['selected_before_scoring'] is False


def paired(tmp_path):
    a=tmp_path/'a';b=tmp_path/'b';a.mkdir();b.mkdir()
    raw,ann=recording(a);raw2,ann2=recording(b)
    rows=[json.loads(x) for x in raw2.read_text().splitlines()]
    for row in rows:
        if row['type']=='session':row['session'].update(session_id='8',clock_id='board:8')
        if row['type']=='info':row['info']['sid']=8
        if row['type']=='state':
            row['state']['sid']=8
            zero=math.pi-.09
            row['state']['theta']=zero+1.05*(row['state']['theta']-zero)
    raw2.write_text(''.join(json.dumps(r)+'\n' for r in rows));pin=hashlib.sha256(raw2.read_bytes()).hexdigest()
    p=b/'report.json';report=json.loads(p.read_text());report['raw_log_sha256']=pin;p.write_text(json.dumps(report))
    annotation=json.loads(ann2.read_text());annotation['source_sha256']=pin;ann2.write_text(json.dumps(annotation))
    def rescale(rows):
        for row in rows:
            v=row['vision'];a=1.6+1.05*(v['image_angle_rad']-1.6);v['image_angle_rad']=a
            v['bob_px']=[250+100*math.sin(a),250+100*math.cos(a)]
    change_camera(b,rescale)
    return raw,ann,raw2,ann2


def test_fit_carries_camera_and_pose_qualification_without_fusing_encoder(tmp_path):
    from cartpole_sdk.identification.workflow import fit_passive_logs
    raw,ann,raw2,ann2=paired(tmp_path)
    result=fit_passive_logs(raw,ann,raw2,ann2)
    assert result['camera_evidence']['required'] is True
    assert result['camera_evidence']['passed'] is True
    assert result['camera_evidence']['training']['all_release_poses_verified']
    assert result['camera_evidence']['validation']['all_release_poses_verified']
    # Synthetic short record can still fail physics gates; passing camera never certifies the fit.
    assert result['recommended_for_hardware_rl'] is False


def test_failed_camera_pose_is_an_explicit_fit_rejection_reason(tmp_path):
    from cartpole_sdk.identification.workflow import fit_passive_logs
    raw,ann,raw2,ann2=paired(tmp_path)
    annotation=json.loads(ann2.read_text());annotation['episodes'][0].pop('pose_board_relative_s');ann2.write_text(json.dumps(annotation))
    result=fit_passive_logs(raw,ann,raw2,ann2)
    assert result['camera_evidence']['passed'] is False and result['accepted'] is False
    assert any('camera' in reason for reason in result['reasons'])


def test_cli_review_releases_is_offline_and_does_not_fit(tmp_path):
    from cartpole_sdk.identification.cli import main
    raw,ann=recording(tmp_path)
    with patch('cartpole_sdk.rig.Rig',side_effect=AssertionError('serial opened')):
        assert main(['review-releases','--input',str(raw),'--annotations',str(ann),'--output',str(tmp_path/'review')])==0
    assert (tmp_path/'review'/'release-overlay.png').exists()
