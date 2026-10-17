"""Requested conditions remain metadata, source-bound and distinct from measurements."""
from copy import deepcopy
from dataclasses import replace
import hashlib,json
from pathlib import Path
from unittest.mock import patch
import pytest

def protocol(**changes):
    from cartpole_sdk.identification.protocol import make_protocol
    return make_protocol('passive',dataset_role='training',run_label='left-right-check',
        angles_deg=[30.,60.],directions=['left','right'],repetitions=2,cart_restraint='held by hand',**changes)

def test_requested_angles_expand_to_unique_conditions_without_measurements():
    p=protocol()
    assert len(p['requested_releases'])==8
    assert len({r['release_id'] for r in p['requested_releases']})==8
    assert p['nominal_angles_only'] is True
    assert p['dataset_role']=='training'
    assert [(r['angle_from_hanging_deg'],r['direction']) for r in p['requested_releases'][:4]]==[(30.,'left'),(30.,'right'),(60.,'left'),(60.,'right')]
    assert all('measured_angle_deg' not in r and 'board_relative_s' not in r for r in p['requested_releases'])

@pytest.mark.parametrize('angles',([0],[181],[float('nan')],[True]))
def test_invalid_requested_pose_is_rejected(angles):
    from cartpole_sdk.identification.protocol import make_protocol
    with pytest.raises(ValueError):make_protocol('passive',angles_deg=angles,cart_restraint='clamp')

def test_invalid_kind_and_duplicate_ids_are_rejected():
    from cartpole_sdk.identification.protocol import make_protocol,validate_protocol
    with pytest.raises(ValueError):make_protocol('pulse',angles_deg=[30],cart_restraint='hand')
    p=protocol();p['requested_releases'][1]['release_id']=p['requested_releases'][0]['release_id']
    with pytest.raises(ValueError):validate_protocol(p,'passive')

def recorded_source(tmp_path):
    from test_system_id_workflow import raw_recording
    from cartpole_sdk.identification.workflow import digest
    raw=tmp_path/'rig-example.jsonl';annotation=raw_recording(raw,41)
    p=protocol();event=dict(type='collection_protocol',protocol=p,protocol_sha256=digest(p))
    raw.write_text(raw.read_text()+json.dumps(event)+'\n')
    report=dict(schema='cartpole-id-run-v1',procedure='passive',completed=True,stop_confirmed=True,records_dropped=0,
        camera={},raw_log=raw.name,raw_log_sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),collection_protocol=p,collection_protocol_sha256=digest(p))
    (tmp_path/'report.json').write_text(json.dumps(report));return raw,p,report

def test_annotation_template_carries_requested_conditions_without_selecting_intervals(tmp_path):
    from cartpole_sdk.identification.workflow import annotation_template
    raw,p,report=recorded_source(tmp_path);a=annotation_template(raw)
    assert a['collection_protocol']==p and a['selected_before_scoring'] is False
    assert a['operator_cart_restraint']=='held by hand'
    assert len(a['requested_releases'])==8 and a['episodes']==[]

@pytest.mark.parametrize('where',('report','raw'))
def test_protocol_tampering_is_rejected(tmp_path,where):
    from cartpole_sdk.identification.workflow import load_records
    raw,p,report=recorded_source(tmp_path)
    if where=='report':
        report['collection_protocol']['requested_releases'][0]['angle_from_hanging_deg']=45
        (tmp_path/'report.json').write_text(json.dumps(report))
    else:
        rows=[json.loads(x) for x in raw.read_text().splitlines()]
        rows[-1]['protocol']['run_label']='changed'
        raw.write_text(''.join(json.dumps(x)+'\n' for x in rows))
        report['raw_log_sha256']=hashlib.sha256(raw.read_bytes()).hexdigest()
        (tmp_path/'report.json').write_text(json.dumps(report))
    with pytest.raises(ValueError,match='protocol'):load_records(raw)

def test_cli_metadata_reaches_real_collector_validation_before_serial(tmp_path):
    from cartpole_sdk.identification.cli import main,parser
    args=['collect-passive','--port','offline','--output',str(tmp_path/'run'),
        '--dataset-role','training','--run-label','passive-set-a','--release-angles-deg','30','60',
        '--release-directions','left','right','--repetitions','2','--cart-restraint','held by hand']
    p=parser().parse_args(args)
    assert p.release_angles_deg==[30.,60.] and p.repetitions==2
    args[args.index('30')]='181'
    with patch('cartpole_sdk.rig.Rig',side_effect=AssertionError('serial opened')):assert main(args)==2
    assert not (tmp_path/'run').exists()


@pytest.mark.parametrize('problem',('missing_report','historical_report','procedure_mismatch','procedure_missing','raw_start_mismatch'))
def test_protocol_cannot_fall_back_to_history_or_contradict_procedure(tmp_path,problem):
    from cartpole_sdk.identification.workflow import load_records
    raw,p,report=recorded_source(tmp_path);report_path=tmp_path/'report.json'
    if problem=='missing_report':report_path.unlink()
    else:
        if problem=='historical_report':report['schema']='historical-unbound'
        elif problem=='procedure_mismatch':report['procedure']='pulse'
        elif problem=='procedure_missing':del report['procedure']
        elif problem=='raw_start_mismatch':
            with raw.open('a') as stream:stream.write(json.dumps(dict(type='ringdown_start'))+'\n')
            report['raw_log_sha256']=hashlib.sha256(raw.read_bytes()).hexdigest()
        report_path.write_text(json.dumps(report))
    with pytest.raises(ValueError):load_records(raw)
