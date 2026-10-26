from dataclasses import asdict
from hashlib import sha256
import json
import zipfile
import pytest
from cartpole_sdk.contracts import Session, Observation, Sample
from cartpole_sdk.portal.run_recording import RunRecorder
from cartpole_sdk.recording import read_recording


def obs(seq, stamp):
    return Observation('s','clock',seq,stamp,'test',(Sample('cart','position','step',.01,'m','cart-step-home','test','valid',None,'estimated',stamp,stamp,stamp),))


def bundle(tmp_path, *, gap=False):
    recorder=RunRecorder(tmp_path,{'id':'job','artifact':'a','source':'magnetic-step'})
    recorder.emit('session',session=asdict(Session('s','clock')))
    recorder.observation(obs(10,10_000_000))
    recorder.observation(obs(10,10_000_000))
    recorder.emit('action_request',sequence=1,observation_sequence=10,acceleration_m_s2=.2,inference_s=.001)
    recorder.observation(obs(30 if gap else 20,30_000_000 if gap else 20_000_000))
    recorder.emit('action_request',sequence=2,observation_sequence=99,acceleration_m_s2=None,inference_s=.001)
    return recorder.finalize('failed',{'stopped':True,'error':'diagnostic'})


def test_export_preserves_observations_and_explicit_action_pairing(tmp_path):
    from cartpole_sdk.portal.dataset import export_bundle
    path=bundle(tmp_path/'spool')
    result=export_bundle(path,tmp_path/'dataset',expected_sha256=sha256(path.read_bytes()).hexdigest())
    session,observations=read_recording(tmp_path/'dataset/observations.jsonl')
    assert session.session_id=='s' and len(observations)==2
    rows=[json.loads(x) for x in (tmp_path/'dataset/transitions.jsonl').read_text().splitlines()]
    assert rows[0]['pairing']=='available' and rows[0]['dt_ns']==10_000_000
    assert rows[0]['requested_acceleration_m_s2']==.2
    assert rows[0]['reward'] is None and rows[0]['physically_applied_action_known'] is False
    assert rows[1]['pairing']=='missing_observation'
    assert result['duplicate_observations']==1
    assert 'effective_ns' in (tmp_path/'dataset/samples.csv').read_text()
    assert (tmp_path/'dataset/telemetry.jsonl').exists()


def test_gap_is_flagged_never_interpolated(tmp_path):
    from cartpole_sdk.portal.dataset import export_bundle
    export_bundle(bundle(tmp_path/'spool',gap=True),tmp_path/'data')
    row=json.loads((tmp_path/'data/transitions.jsonl').read_text().splitlines()[0])
    assert row['pairing']=='time_gap' and row['dt_ns']==20_000_000


def test_wrong_digest_and_zip_members_refused_before_output(tmp_path):
    from cartpole_sdk.portal.dataset import export_bundle
    path=bundle(tmp_path/'spool')
    with pytest.raises(ValueError,match='digest'):export_bundle(path,tmp_path/'out',expected_sha256='0'*64)
    assert not (tmp_path/'out').exists()
    bad=tmp_path/'bad.zip'
    with zipfile.ZipFile(bad,'w') as z:
        z.writestr('../escape','bad')
    with pytest.raises(ValueError):export_bundle(bad,tmp_path/'out')
    assert not (tmp_path/'out').exists()


def test_recording_error_and_action_identity_preserved(tmp_path):
    from cartpole_sdk.portal.dataset import export_bundle
    path=bundle(tmp_path/'spool')
    with zipfile.ZipFile(path) as z:
        manifest=json.loads(z.read('manifest.json'));telemetry=z.read('telemetry.jsonl')
    manifest['recording']['error']='telemetry_flush_failed'
    changed=tmp_path/'incomplete.zip'
    with zipfile.ZipFile(changed,'w') as z:
        z.writestr('manifest.json',json.dumps(manifest));z.writestr('telemetry.jsonl',telemetry)
    export_bundle(changed,tmp_path/'data')
    row=json.loads((tmp_path/'data/transitions.jsonl').read_text().splitlines()[0])
    assert row['action_sequence']==1 and row['action_recorded_monotonic_ns']>0
    assert row['recording_incomplete'] is True
    assert row['recording_error']=='telemetry_flush_failed'


def test_missing_coverage_counters_rejected(tmp_path):
    from cartpole_sdk.portal.dataset import export_bundle
    path=bundle(tmp_path/'spool')
    with zipfile.ZipFile(path) as z:
        manifest=json.loads(z.read('manifest.json'));telemetry=z.read('telemetry.jsonl')
    del manifest['recording']['dropped_records']
    changed=tmp_path/'bad.zip'
    with zipfile.ZipFile(changed,'w') as z:
        z.writestr('manifest.json',json.dumps(manifest));z.writestr('telemetry.jsonl',telemetry)
    with pytest.raises(ValueError,match='recording counters'):export_bundle(changed,tmp_path/'data')


def test_policy_inputs_exclude_preflight_and_terminal_only_observations(tmp_path):
    from cartpole_sdk.portal.dataset import export_bundle
    recorder=RunRecorder(tmp_path/'spool',{'id':'job','artifact':'a','source':'simulation'})
    recorder.emit('session',session=asdict(Session('s','clock')))
    recorder.observation(obs(0,0))
    recorder.observation(obs(10,10_000_000))
    recorder.emit('policy_call',observation_sequence=10)
    recorder.emit('action_request',sequence=1,observation_sequence=10,acceleration_m_s2=0.,inference_s=.001)
    recorder.observation(obs(20,20_000_000))
    path=recorder.finalize('succeeded',{'stopped':True})
    result=export_bundle(path,tmp_path/'data')
    _,observations=read_recording(tmp_path/'data/policy-inputs.jsonl')
    assert [o.sequence for o in observations]==[10]
    assert result['policy_input_selection']=='policy_call markers'
    assert result['observations']==3
