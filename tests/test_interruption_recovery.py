"""Interrupted input requires a narrow, reproducible proof, never a rewritten report."""
import hashlib
import json

import pytest

from test_release_review import recording, _write, _rows, _hash, bind_camera_report
from cartpole_sdk.identification import workflow


def interrupted(tmp_path):
    raw, annotations = recording(tmp_path)
    rows = [json.loads(line) for line in raw.read_text().splitlines()]
    session, info = rows[:2]
    baseline = rows[3]['baseline']
    states = rows[4:]
    for row in states:
        row['host_monotonic_ns'] = row['state']['received_ns'] + 1000
    start = dict(type='passive_start', seconds=120., measurement_version=2,
                 baseline_sha256=workflow.digest(baseline), info=info['info'], state=states[200]['state'],
                 host_monotonic_ns=12_000_002_000)
    rows = [dict(session,host_monotonic_ns=9_990_000_000),dict(info,host_monotonic_ns=9_995_000_000)] + states[:201] + [
        dict(type='passive_baseline', baseline=baseline, host_monotonic_ns=12_000_001_500),start] + states[201:] + [
        dict(type='passive_failure', reason='KeyboardInterrupt()', host_monotonic_ns=14_501_000_000),
        dict(type='command', payload='V2 STOP 7', host_monotonic_ns=14_502_000_000),
        dict(type='reply', payload='V2 OK 7 STOP', host_monotonic_ns=14_503_000_000),
        dict(type='state',state=dict(states[-1]['state'],received_ns=14_510_000_000,unwrapped_us=4_510_000,unwrapped_tick=4510),host_monotonic_ns=14_510_001_000),
        dict(type='termination', error=None, records_dropped=0,host_monotonic_ns=14_511_000_000)]
    _rows(raw, rows)
    camera = tmp_path/'vision.ndjson'
    frames=[json.loads(line) for line in camera.read_text().splitlines()]
    for row in frames: row['vision']['age_since_host_read_s']=.001
    _rows(camera,frames)
    vr=json.loads((tmp_path/'vision-report.json').read_text())
    vr.update(failure='KeyboardInterrupt()',sha256=_hash(camera),frames=226,heartbeat_records=0,stream_records=226,
              started_ns=8_998_000_000,finished_ns=16_002_000_000)
    _write(tmp_path/'vision-report.json',vr)
    _write(tmp_path/'report.json',dict(schema='cartpole-id-run-v1',procedure='passive',raw_log=raw.name,
        raw_log_sha256=_hash(raw),completed=False,failure='KeyboardInterrupt()',records_dropped=0,camera=vr,
        started_ns=9_000_000_000,finished_ns=16_003_000_000))
    a=json.loads(annotations.read_text());a['source_sha256']=_hash(raw);_write(annotations,a)
    return raw, annotations


def recover(raw):
    from cartpole_sdk.identification.interruption_recovery import recover_passive
    return recover_passive(raw,reason='Operator explicitly ended collection with Ctrl-C after releases were done.')


def rebind_raw(raw, change):
    rows=[json.loads(line) for line in raw.read_text().splitlines()];change(rows);_rows(raw,rows)
    report=json.loads((raw.parent/'report.json').read_text());report['raw_log_sha256']=_hash(raw)
    _write(raw.parent/'report.json',report)


def test_explicit_recovery_preserves_originals_and_proves_partial_completion(tmp_path):
    raw,ann=interrupted(tmp_path)
    before={p.name:p.read_bytes() for p in tmp_path.iterdir()}
    with pytest.raises(ValueError,match='failed recording'):workflow.load_records(raw)
    sidecar=recover(raw)
    assert sidecar==tmp_path/'recovery.json'
    assert all((tmp_path/name).read_bytes()==value for name,value in before.items())
    records,identity=workflow.load_records(raw)
    proof=identity['interruption_recovery']
    assert proof['completion_kind']=='operator-ended partial'
    assert proof['requested_duration_s']==120.
    assert proof['actual_duration_s']==pytest.approx(2.500998)
    assert proof['original_collection_failure']=='KeyboardInterrupt()'
    assert proof['original_camera_failure']=='KeyboardInterrupt()'
    assert identity['collection_report']['completed'] is False
    assert identity['collection_report']['sha256']==hashlib.sha256(before['report.json']).hexdigest()
    from cartpole_sdk.identification.release_review import analyze_releases
    review=analyze_releases(raw,ann)
    assert review['passed'] and review['all_release_poses_verified']
    assert review['source_identity']['interruption_recovery']==proof
    assert json.loads((tmp_path/'report.json').read_text())['completed'] is False
    with pytest.raises(FileExistsError):recover(raw)


@pytest.mark.parametrize('mutation',('failure','drop','termination','stop_command','stop_reply','post_stop_state',
    'stop_before_interrupt','arm','action','enabled','reference','baseline','start','camera_error','camera_count',
    'camera_hash','camera_stale','camera_clock','board_clock','unexpected_event','partial_line'))
def test_recovery_rejects_ambiguous_or_failed_recordings(tmp_path,mutation):
    raw,ann=interrupted(tmp_path)
    if mutation in ('camera_error','camera_count','camera_hash','camera_clock'):
        v=json.loads((tmp_path/'vision-report.json').read_text())
        if mutation=='camera_error':v['failure']='TimeoutError()'
        elif mutation=='camera_count':v['stream_records']+=1
        elif mutation=='camera_hash':v['sha256']='0'*64
        else:v['clock_sync']['end']['offset_ns']+=50_000_000
        bind_camera_report(tmp_path,v)
    elif mutation=='camera_stale':
        path=tmp_path/'vision.ndjson';rows=[json.loads(line) for line in path.read_text().splitlines()]
        rows[-1]['vision']['stale']=True;_rows(path,rows)
        v=json.loads((tmp_path/'vision-report.json').read_text());v['sha256']=_hash(path);bind_camera_report(tmp_path,v)
    elif mutation=='partial_line':
        raw.write_bytes(raw.read_bytes().rstrip(b'\n'))
        r=json.loads((tmp_path/'report.json').read_text());r['raw_log_sha256']=_hash(raw);_write(tmp_path/'report.json',r)
    else:
        def change(rows):
            if mutation=='failure':rows[-5]['reason']='RuntimeError()'
            elif mutation=='drop':rows[-1]['records_dropped']=1
            elif mutation=='termination':rows[-1]['error']='transport failed'
            elif mutation=='stop_command':rows.pop(-4)
            elif mutation=='stop_reply':rows.pop(-3)
            elif mutation=='post_stop_state':rows.pop(-2)
            elif mutation=='stop_before_interrupt':rows[-4],rows[-5]=rows[-5],rows[-4]
            elif mutation=='arm':rows.insert(2,dict(type='command',payload='V2 ARM 7',host_monotonic_ns=9_999_000_000))
            elif mutation=='action':rows.insert(2,dict(type='action_request',request={},host_monotonic_ns=9_999_000_000))
            elif mutation=='enabled':rows[30]['state']['flags']=207
            elif mutation=='reference':rows[1]['info']['home_epoch']=3
            elif mutation=='baseline':next(r for r in rows if r['type']=='passive_start')['baseline_sha256']='0'*64
            elif mutation=='start':rows[:]=[r for r in rows if r['type']!='passive_start']
            elif mutation=='board_clock':rows[40]['state']['unwrapped_us']=1
            else:rows.insert(-1,dict(type='bad_frame',reason='CRC',host_monotonic_ns=14_510_500_000))
        rebind_raw(raw,change)
    with pytest.raises(ValueError):recover(raw)
    assert not (tmp_path/'recovery.json').exists()


@pytest.mark.parametrize('target',('raw','report','camera','vision_report','recovery'))
def test_each_recovered_load_revalidates_bound_evidence(tmp_path,target):
    raw,ann=interrupted(tmp_path);recover(raw)
    path={'raw':raw,'report':tmp_path/'report.json','camera':tmp_path/'vision.ndjson',
          'vision_report':tmp_path/'vision-report.json','recovery':tmp_path/'recovery.json'}[target]
    if target=='recovery':
        value=json.loads(path.read_text());value['evidence']['actual_duration_s']=120.;_write(path,value)
    else:path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(ValueError):workflow.load_records(raw)


@pytest.mark.parametrize('field,value',(
    ('stop_records',[{'type':'stop_failure','reason':'unconfirmed'}]),
    ('options',{'seconds':180.}),
    ('expected_reference',101),
    ('expected_home',3),
))
def test_recovery_rejects_report_metadata_contradicting_raw_evidence(tmp_path,field,value):
    raw,ann=interrupted(tmp_path)
    path=tmp_path/'report.json';report=json.loads(path.read_text());report[field]=value;_write(path,report)
    with pytest.raises(ValueError):recover(raw)
    assert not (tmp_path/'recovery.json').exists()


def trim_camera(tmp_path, *, source_end=104.3, last_receipt=None, uncertainty_ns=None):
    path=tmp_path/'vision.ndjson'
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    rows=[r for r in rows if r['vision']['t']<=source_end]
    if last_receipt is not None:rows[-1]['collector_received_ns']=last_receipt
    _rows(path,rows)
    report=json.loads((tmp_path/'vision-report.json').read_text())
    report.update(sha256=_hash(path),frames=len(rows),stream_records=len(rows))
    if uncertainty_ns is not None:
        for anchor in report['clock_sync'].values():
            if not isinstance(anchor,dict):continue
            midpoint=(anchor['local_before_ns']+anchor['local_after_ns'])//2
            anchor.update(local_before_ns=midpoint-uncertainty_ns,local_after_ns=midpoint+uncertainty_ns,
                          uncertainty_ns=uncertainty_ns)
        report.update(started_ns=8_989_000_000,finished_ns=16_020_000_000)
    bind_camera_report(tmp_path,report)


def test_fresh_stop_state_cannot_rescue_stalled_pre_interrupt_encoder(tmp_path):
    raw,ann=interrupted(tmp_path)
    rebind_raw(raw,lambda rows:rows.__setitem__(slice(None),[r for r in rows if not
        (r['type']=='state' and 14_400_000_000<=r['state']['received_ns']<=14_500_000_000)]))
    with pytest.raises(ValueError,match='fresh.*encoder|encoder.*fresh'):recover(raw)
    assert not (tmp_path/'recovery.json').exists()


@pytest.mark.parametrize('last_receipt',(None,14_500_000_000,14_502_000_000))
def test_interrupt_cannot_mask_stalled_camera_even_with_fresh_or_later_receipt(tmp_path,last_receipt):
    raw,ann=interrupted(tmp_path)
    trim_camera(tmp_path,last_receipt=last_receipt)
    with pytest.raises(ValueError,match='fresh.*camera|camera.*fresh'):recover(raw)
    assert not (tmp_path/'recovery.json').exists()


def test_camera_freshness_uses_conservative_clock_uncertainty_bound(tmp_path):
    raw,ann=interrupted(tmp_path)
    # Last source maps to14.36s:141ms before interrupt, but151ms at
    # the early edge of its +/-10ms synchronization uncertainty.
    trim_camera(tmp_path,source_end=104.36,uncertainty_ns=10_000_000)
    with pytest.raises(ValueError,match='fresh.*camera|camera.*fresh'):recover(raw)
    assert not (tmp_path/'recovery.json').exists()


def test_fresh_camera_within_uncertainty_bound_remains_recoverable(tmp_path):
    raw,ann=interrupted(tmp_path)
    trim_camera(tmp_path,source_end=104.36)
    recover(raw)
    proof=workflow.load_records(raw)[1]['interruption_recovery']
    assert proof['interruption_freshness']['encoder_receipt_age_ns']==1_000_000
    assert proof['interruption_freshness']['camera_receipt_age_ns']==139_000_000
    assert proof['interruption_freshness']['camera_source_age_upper_bound_ns']==pytest.approx(142_000_000,abs=100)


def redundant_stop_with_reply_logged_first(raw):
    def change(rows):
        # Serial write precedes command logging; the receiver can log its ACK
        # first. Keep the earlier ordered STOP pair and every timestamp intact.
        rows[-2:-2]=[
            dict(type='reply',payload='V2 OK 7 STOP',host_monotonic_ns=14_504_000_000),
            dict(type='command',payload='V2 STOP 7',host_monotonic_ns=14_505_000_000),
            dict(type='command',payload='V2 STATUS 7',host_monotonic_ns=14_506_000_000)]
    rebind_raw(raw,change)


def test_redundant_stop_logging_race_keeps_ordered_ack_and_fresh_final_state(tmp_path):
    raw,ann=interrupted(tmp_path);redundant_stop_with_reply_logged_first(raw)
    before=raw.read_bytes()
    recover(raw)
    records,identity=workflow.load_records(raw)
    proof=identity['interruption_recovery']['final_stop']
    command=records[proof['command_record']]
    ack=records[proof['acknowledgement_record']]
    last_stop=records[proof['last_stop_command_record']]
    state=records[proof['disabled_state_record']]
    assert command['host_monotonic_ns']==14_502_000_000
    assert ack['host_monotonic_ns']==14_503_000_000
    assert last_stop['host_monotonic_ns']==14_505_000_000
    assert records[proof['last_command_record']]['payload']=='V2 STATUS 7'
    assert state['state']['received_ns']==14_510_000_000
    assert raw.read_bytes()==before


@pytest.mark.parametrize('problem',('all_ack_missing','non_stop_after','no_final_state','late_stop_clock'))
def test_redundant_stop_does_not_relax_required_shutdown_evidence(tmp_path,problem):
    raw,ann=interrupted(tmp_path);redundant_stop_with_reply_logged_first(raw)
    def change(rows):
        if problem=='all_ack_missing':rows[:]=[r for r in rows if r.get('payload')!='V2 OK 7 STOP']
        elif problem=='non_stop_after':rows[-3]['payload']='V2 INFO 7'
        elif problem=='no_final_state':rows.pop(-2)
        else:rows[-4]['host_monotonic_ns']=14_512_000_000
    rebind_raw(raw,change)
    with pytest.raises(ValueError):recover(raw)
    assert not (tmp_path/'recovery.json').exists()


def freeze_pre_interrupt_snapshots(raw, first_receipt):
    def change(rows):
        snapshot=next(r['state'] for r in rows if r['type']=='state' and r['state']['received_ns']==first_receipt)
        for row in rows:
            if row['type']=='state' and first_receipt<row['state']['received_ns']<=14_500_000_000:
                row['state']=dict(snapshot,received_ns=row['state']['received_ns'])
    rebind_raw(raw,change)


def test_fresh_duplicate_receipts_cannot_rescue_frozen_board_snapshot(tmp_path):
    raw,ann=interrupted(tmp_path)
    freeze_pre_interrupt_snapshots(raw,14_400_000_000)
    with pytest.raises(ValueError,match='fresh.*encoder|encoder.*fresh'):recover(raw)
    assert not (tmp_path/'recovery.json').exists()


def test_short_duplicate_snapshot_uses_first_receipt_and_remains_recoverable(tmp_path):
    raw,ann=interrupted(tmp_path)
    freeze_pre_interrupt_snapshots(raw,14_490_000_000)
    recover(raw)
    proof=workflow.load_records(raw)[1]['interruption_recovery']
    assert proof['interruption_freshness']['encoder_receipt_age_ns']==11_000_000
