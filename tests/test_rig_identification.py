"""Actual rig log ingestion preserves faults, input meaning and identities."""
import pytest
import cartpole_sdk.identification as identification


def records():
    header = dict(type='session', session=dict(session_id='7', clock_id='teensy:7'))
    info = dict(type='info', info=dict(sid=7, firmware='executor-v6-measuredrail',
                encoder_upright_raw=330, home_epoch=2))
    states = [dict(type='state',state=dict(sid=7, unwrapped_tick=i+1,
        unwrapped_us=1000000+i*4000, theta=.1+i*.01, angle_hat=.4, omega=9.,
        acceleration=1.2, demand=22., mode=3, flags=207, fault=0, misses=0,
        x=.02, velocity=.1, received_ns=5000000000+i*4000000)) for i in range(4)]
    return [header, info, *states]


def adapt(data):
    assert hasattr(identification, 'rig_log_rows'), 'rig JSONL adapter is missing'
    return identification.rig_log_rows(data, run_id='run-a')


def test_rig_adapter_uses_unfiltered_angle_executed_command_and_board_clock():
    rows, summary = adapt(records())
    assert rows[0]['t_s'] == 1.
    assert rows[0]['theta_rad'] == .1
    assert rows[0]['cart_acceleration_m_s2'] == 1.2
    assert rows[0]['acceleration_kind'] == 'commanded'
    assert rows[0]['clock_id'] == 'teensy:7'
    assert rows[0]['calibration_id'].endswith(':330')
    assert 'omega_rad_s' not in rows[0]  # MCU filtered-rate delay is not calibrated.
    assert summary['eligible_states'] == 4


def test_faults_and_noncontrol_modes_stay_in_data_as_invalid_boundaries():
    data=records()
    data[3]['state']['fault']=4
    data[4]['state']['mode']=14
    rows, summary=adapt(data)
    assert [r['valid'] for r in rows] == [True, False, False, True]
    assert summary['eligible_states'] == 2
    assert summary['excluded_states'] == 2


def test_reference_changes_split_identity_and_identical_retransmits_are_counted():
    data=records()
    duplicate=dict(data[2], state=dict(data[2]['state'], received_ns=5001000000))
    data.insert(3, duplicate)
    data.insert(5,dict(type='info', info=dict(data[1]['info'],encoder_upright_raw=351)))
    rows, summary=adapt(data)
    assert len(rows)==4
    assert summary['duplicate_states']==1
    assert rows[1]['calibration_id'] != rows[2]['calibration_id']


@pytest.mark.parametrize('change', ['conflicting_duplicate','clock_rollback','session','missing_reference','nan'])
def test_ambiguous_recordings_are_rejected(change):
    data=records()
    if change=='conflicting_duplicate':
        data.insert(3,dict(data[2],state=dict(data[2]['state'],theta=.2)))
    elif change=='clock_rollback': data[4]['state']['unwrapped_us']=500000
    elif change=='session': data[4]['state']['sid']=8
    elif change=='missing_reference': data.pop(1)
    else: data[3]['state']['acceleration']=float('nan')
    with pytest.raises(ValueError): adapt(data)


def test_cli_reads_archives_without_extraction_and_keeps_hashes(tmp_path):
    import io, json, subprocess, sys, tarfile
    archive=tmp_path/'records.tar.gz'
    with tarfile.open(archive,'w:gz') as tar:
        for name in ('train.jsonl','test.jsonl'):
            data=records()
            if name=='test.jsonl':
                data[0]['session']=dict(session_id='8',clock_id='teensy:8')
                data[1]['info']['sid']=8
                for record in data[2:]: record['state']['sid']=8
            raw=('\n'.join(json.dumps(r) for r in data)+'\n').encode()
            member=tarfile.TarInfo(name);member.size=len(raw)
            tar.addfile(member,io.BytesIO(raw))
    output=tmp_path/'report.json'
    run=subprocess.run([sys.executable,'examples/identify_rig.py','--training',str(archive)+'::train.jsonl',
        '--validation',str(archive)+'::test.jsonl','--output',str(output)],capture_output=True,text=True)
    assert run.returncode==2, run.stderr  # deliberately too little excitation
    report=json.loads(output.read_text())
    assert not report['accepted']
    inputs=report['provenance']['supplied']['inputs']
    assert len(inputs['training']['sha256'])==64
    assert inputs['training']['sha256'] != inputs['validation']['sha256']
    assert inputs['training']['admission']['eligible_states']==4
    assert not (tmp_path/'train.jsonl').exists()
