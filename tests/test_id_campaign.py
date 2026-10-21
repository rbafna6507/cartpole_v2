"""Campaign contracts, offline artifacts and fail-closed orchestration."""
import json
from pathlib import Path
import tarfile
import pytest

from cartpole_sdk.identification import campaign as c


def test_plans_are_bounded_and_separate_manual_from_powered():
    plan=c.plan_suite('autonomous',repetitions=2)
    assert plan['requires_execute'] and plan['rate_hz']==100
    assert {t['kind'] for t in plan['trials']}=={'actuator','timing','coupled'}
    assert len({t['id'] for t in plan['trials']})==len(plan['trials'])
    assert not c.plan_suite('angle-map')['requires_execute']
    assert c.plan_suite('cart-map')['requires_physical_home_after']
    for kw in ({'suite':'all'}, {'suite':'timing','seconds':float('nan')},
               {'suite':'actuator','repetitions':0}, {'suite':'timing','repetitions':True}):
        with pytest.raises(ValueError):c.plan_suite(**kw)


def test_no_authorization_or_manual_restraint_fails_before_resources(tmp_path):
    def never(*a,**k):raise AssertionError('resource must not open')
    for kw in ({'suite':'autonomous'}, {'suite':'angle-map'}):
        out=tmp_path/kw['suite']
        with pytest.raises(ValueError):
            c.collect_campaign(output=out,port='offline',rig_factory=never,camera_factory=never,**kw)
        assert not out.exists()


def test_rehearsal_review_bundle_preserves_synthetic_not_physical(tmp_path):
    folder=tmp_path/'rehearsal'
    report=c.rehearse(folder,suite='timing')
    assert report['synthetic'] and not report['hardware_accepted']
    assert (folder/'manifest.json').exists()
    review=c.review_campaign(folder,tmp_path/'review')
    assert review['integrity_ok'] and not review['ready_for_fit']
    assert 'synthetic' in ' '.join(review['blockers']).lower()
    package=tmp_path/'package.tar.gz'
    c.bundle_campaign(folder,package)
    with tarfile.open(package) as archive:
        assert 'rehearsal/manifest.json' in archive.getnames()
        assert 'rehearsal/rig.jsonl' in archive.getnames()
    with pytest.raises(FileExistsError):c.rehearse(folder,suite='timing')
    with pytest.raises(FileExistsError):c.bundle_campaign(folder,package)


def test_tampering_extra_files_symlinks_and_nested_package_rejected(tmp_path):
    folder=tmp_path/'recording';c.rehearse(folder,suite='timing')
    with pytest.raises(ValueError):c.bundle_campaign(folder,folder/'bad.tar.gz')
    (folder/'rig.jsonl').write_text('{}\n')
    with pytest.raises(ValueError,match='integrity'):c.bundle_campaign(folder,tmp_path/'bad.tar.gz')
    review=c.review_campaign(folder,tmp_path/'review')
    assert not review['integrity_ok'] and not review['ready_for_fit']
    folder2=tmp_path/'recording2';c.rehearse(folder2,suite='timing')
    (folder2/'extra').symlink_to(folder/'rig.jsonl')
    with pytest.raises(ValueError):c.bundle_campaign(folder2,tmp_path/'bad2.tar.gz')


def test_failure_archive_stays_reviewable(tmp_path):
    folder=tmp_path/'failed';folder.mkdir()
    c.write_json(folder/'report.json',{'schema':c.SCHEMA,'completed':False,'synthetic':False,
        'failure':'injected','stop_confirmed':False,'records_dropped':0,'trials':[]})
    c.seal(folder)
    report=c.review_campaign(folder,tmp_path/'review')
    assert report['integrity_ok'] and not report['ready_for_fit']
    assert any('STOP' in b for b in report['blockers'])
    c.bundle_campaign(folder,tmp_path/'failed.tar.gz')


def test_help_and_plan_do_not_load_serial_or_camera(monkeypatch,capsys):
    from cartpole_sdk.identification.campaign_cli import main
    import builtins
    original=builtins.__import__
    def guarded(name,*a,**kw):
        if name in ('serial','urllib.request'):raise AssertionError(name)
        return original(name,*a,**kw)
    monkeypatch.setattr(builtins,'__import__',guarded)
    assert main(['plan','--suite','angle-map'])==0
    assert 'angle-map' in capsys.readouterr().out


def fake_resources(tmp_path, monkeypatch, *, fail_at=None, camera_failure=False, changed_settings=False):
    from types import SimpleNamespace
    from cartpole_sdk.identification import driven_capture as d
    instances=[]; calls=[]
    class Camera:
        def __init__(self,url,folder,budget):self.folder=Path(folder)
        def start(self):
            (self.folder/'vision.ndjson').write_text('')
            if camera_failure:raise RuntimeError('camera unavailable')
        def close(self):return {'failure':'camera unavailable'} if camera_failure else {}
    class Rig:
        def __init__(self,port,**kw):
            self.records_dropped=0;self.error=None;self.n=0
            self.state=SimpleNamespace(enabled=False)
            self.log_path=kw['log_dir']/'rig.jsonl';self.log_path.write_text('')
            instances.append(self)
        def __enter__(self):return self
        def __exit__(self,*a):self.stop()
        def stop(self):calls.append('stop');self.state.enabled=False
        def _stopped_healthy(self):pass
        def get_info(self):return SimpleNamespace(encoder_upright_raw=351,home_epoch=8)
        def get_parameters(self):
            self.n+=1
            return {'jmax':150 if not changed_settings or self.n<3 else 300}
        def _record(self,event,**kw):
            with self.log_path.open('a') as f:f.write(json.dumps(dict(type=event,**kw))+'\n')
    def run(*a,**kw):
        calls.append('trial')
        if calls.count('trial')==fail_at:raise RuntimeError('fault during trial')
        return {'completed':True}
    monkeypatch.setattr(c,'_settle',lambda *a,**kw:None)
    monkeypatch.setattr(d,'run_timing_hold',run)
    monkeypatch.setattr(d,'return_saved_home',lambda *a,**kw:calls.append('return') or {})
    return Rig,Camera,instances,calls


def test_fault_aborts_campaign_no_next_trial_or_fault_rehome(tmp_path,monkeypatch):
    Rig,Camera,instances,calls=fake_resources(tmp_path,monkeypatch,fail_at=2)
    folder=tmp_path/'fault'
    with pytest.raises(RuntimeError,match='fault during trial'):
        c.collect_campaign(output=folder,port='fixture',suite='timing',execute=True,
                           repetitions=3,rig_factory=Rig,camera_factory=Camera,emit=lambda x:None)
    assert calls.count('trial')==2 and calls.count('return')==1 and calls[-1]=='stop'
    report=json.loads((folder/'report.json').read_text())
    assert not report['completed'] and len(report['trials'])==2
    assert report['trials'][0]['completed'] and not report['trials'][1]['completed']
    assert c.verify(folder)==(True,None)


def test_changed_parameters_abort_before_next_trial(tmp_path,monkeypatch):
    Rig,Camera,instances,calls=fake_resources(tmp_path,monkeypatch,changed_settings=True)
    with pytest.raises(ValueError,match='parameters changed'):
        c.collect_campaign(output=tmp_path/'changed',port='fixture',suite='timing',execute=True,
                           repetitions=2,rig_factory=Rig,camera_factory=Camera,emit=lambda x:None)
    assert calls.count('trial')==1


def test_camera_failure_prevents_any_serial_session(tmp_path,monkeypatch):
    Rig,Camera,instances,calls=fake_resources(tmp_path,monkeypatch,camera_failure=True)
    folder=tmp_path/'failedcamera'
    with pytest.raises(RuntimeError,match='camera unavailable'):
        c.collect_campaign(output=folder,port='fixture',suite='timing',execute=True,
                           rig_factory=Rig,camera_factory=Camera,emit=lambda x:None)
    assert instances==[] and c.verify(folder)==(True,None)


def test_success_requires_stop_and_preserves_plan_and_settings(tmp_path,monkeypatch):
    Rig,Camera,instances,calls=fake_resources(tmp_path,monkeypatch)
    folder=tmp_path/'success'
    report=c.collect_campaign(output=folder,port='fixture',suite='timing',execute=True,
        rig_factory=Rig,camera_factory=Camera,emit=lambda x:None)
    assert report['completed'] and report['stop_confirmed'] and not report['hardware_accepted']
    assert calls.count('trial')==2 and calls.count('return')==2
    assert c.verify(folder)==(True,None)


def test_nested_manifest_is_not_exempt_from_integrity(tmp_path):
    folder=tmp_path/'synthetic';c.rehearse(folder,suite='timing')
    (folder/'nested').mkdir();(folder/'nested'/'manifest.json').write_text('{}')
    assert not c.verify(folder)[0]


def test_connection_failure_without_first_state_still_seals_evidence(tmp_path,monkeypatch):
    Rig,Camera,instances,calls=fake_resources(tmp_path,monkeypatch)
    class MissingState(Rig):
        def __enter__(self):raise RuntimeError('connect failed')
        @property
        def state(self):raise RuntimeError('no state')
        @state.setter
        def state(self,value):pass
    folder=tmp_path/'connectfailure'
    with pytest.raises(RuntimeError,match='connect failed'):
        c.collect_campaign(output=folder,port='fixture',suite='timing',execute=True,
            rig_factory=MissingState,camera_factory=Camera,emit=lambda x:None)
    assert c.verify(folder)==(True,None)
    report=json.loads((folder/'report.json').read_text())
    assert not report['completed'] and report['last_disabled_snapshot'] is None


def test_logger_is_drained_before_report_and_manifest(tmp_path,monkeypatch):
    import threading,time
    Rig,Camera,instances,calls=fake_resources(tmp_path,monkeypatch)
    class SlowClose(Rig):
        def __exit__(self,*a):
            super().__exit__(*a)
            def late():
                time.sleep(.08)
                self._record('late_logger_record')
            self._logger=threading.Thread(target=late);self._logger.start()
    folder=tmp_path/'drain'
    c.collect_campaign(output=folder,port='fixture',suite='timing',execute=True,
        rig_factory=SlowClose,camera_factory=Camera,emit=lambda x:None)
    assert not instances[0]._logger.is_alive()
    assert 'late_logger_record' in (folder/'rig.jsonl').read_text()
    assert c.verify(folder)==(True,None)


def test_stuck_logger_cannot_seal_or_claim_success(tmp_path,monkeypatch):
    Rig,Camera,instances,calls=fake_resources(tmp_path,monkeypatch)
    class StuckLogger:
        def join(self,timeout):pass
        def is_alive(self):return True
    class StuckClose(Rig):
        def __exit__(self,*a):super().__exit__(*a);self._logger=StuckLogger()
    folder=tmp_path/'stuck'
    with pytest.raises(RuntimeError,match='logger'):
        c.collect_campaign(output=folder,port='fixture',suite='timing',execute=True,
            rig_factory=StuckClose,camera_factory=Camera,emit=lambda x:None)
    report=json.loads((folder/'report.json').read_text())
    assert not report['completed'] and not report['sealed']
    assert not (folder/'manifest.json').exists()


def test_empty_telemetry_and_sparse_camera_cannot_pass_review(tmp_path):
    folder=tmp_path/'empty';c.rehearse(folder,suite='timing')
    (folder/'manifest.json').unlink()
    report=json.loads((folder/'report.json').read_text());report['synthetic']=False
    report['trials']=[{'id':'001-timing','kind':'timing','started_ns':1_000_000_000,'finished_ns':16_000_000_000,'completed':True}]
    (folder/'report.json').write_text(json.dumps(report))
    (folder/'rig.jsonl').write_text('')
    first=(folder/'vision.ndjson').read_text().splitlines()[0]
    (folder/'vision.ndjson').write_text(first+'\n');c.seal(folder)
    review=c.review_campaign(folder,tmp_path/'empty-review')
    assert not review['analysis_usable']
    assert any('telemetry' in b.lower() for b in review['blockers'])
    assert any('camera' in b.lower() for b in review['blockers'])


def test_json_and_line_limits_apply_before_parse(tmp_path,monkeypatch):
    folder=tmp_path/'oversize';folder.mkdir()
    monkeypatch.setattr(c,'MAX_JSON_BYTES',32)
    (folder/'manifest.json').write_text(' '*33)
    assert not c.verify(folder)[0]
    path=tmp_path/'long.jsonl';path.write_text(' '*100+'\n')
    monkeypatch.setattr(c,'MAX_LINE_BYTES',32)
    with pytest.raises(ValueError,match='line'):list(c._read_lines(path))


@pytest.mark.parametrize('encoder_only', [False, True])
def test_complete_campaign_through_real_sdk_guards_and_scripted_device(tmp_path,monkeypatch,encoder_only):
    """Only device scheduling is scripted; run the actual policies, leases and returns."""
    from dataclasses import replace
    from types import SimpleNamespace
    from test_id_driven_capture import DrivenRig,Camera as CameraFrames,clocks
    from test_rig_console import ScriptedClock
    clock=ScriptedClock();clock.now_ns=0;instances=[]
    class Device(DrivenRig):
        def __init__(self,port,**kw):
            folder=kw.pop('log_dir');kw.pop('vision_publisher');kw.pop('transport_factory')
            super().__init__(port,clock=clock,**kw)
            self.log_path=folder/'rig.jsonl';self.log_path.write_text('')
            self._state=replace(self._state,theta=3.141592653589793,angle_hat=3.141592653589793,omega=0.,x=0.)
            self._info=SimpleNamespace(firmware='executor-v6-measuredrail',encoder_upright_raw=330,
                reference_saved=True,encoder_conf_valid=True,home_epoch=14,measured_span_steps=16000,rail_half_m=.26)
            instances.append(self)
        def _record(self,kind,**data):
            super()._record(kind,**data)
            with self.log_path.open('a') as stream:stream.write(json.dumps(self.records[-1])+'\n')
    class Camera(CameraFrames):
        def __init__(self,url,folder,seconds):
            super().__init__(clock);self.path=folder/'vision.ndjson';self.path.write_text('')
        def start(self):pass
        def close(self):return {}
    with clocks(clock),__import__('unittest.mock',fromlist=['patch']).patch.object(c,'time',clock):
        report=c.collect_campaign(output=tmp_path/'sdk-campaign',port='scripted-device',suite='autonomous',
            execute=True,repetitions=1,seconds=5,encoder_only=encoder_only,
            rig_factory=Device,camera_factory=Camera,emit=lambda x:None)
    assert report['completed'] and report['stop_confirmed'] and len(report['trials'])==8
    commands=[item[1] for item in instances[0].commands]
    assert commands.count('ARM')==7 and commands.count('MODE')==1 and commands.count('REHOME')==8
    assert not {'HOME','CLEAR','SET','CALIBRATE'} & set(commands)
    assert c.verify(tmp_path/'sdk-campaign')==(True,None)
    assert report['sensor_mode'] == ('encoder_only' if encoder_only else 'encoder_camera')
    assert (tmp_path/'sdk-campaign'/'vision.ndjson').exists() is not encoder_only


def test_encoder_only_cli_preserves_explicit_measurement_limitations(tmp_path,monkeypatch,capsys):
    from cartpole_sdk.identification.campaign_cli import main
    import cartpole_sdk.rig
    import cartpole_sdk.identification.experiments as experiments
    Rig,Camera,instances,calls=fake_resources(tmp_path,monkeypatch)
    monkeypatch.setattr(cartpole_sdk.rig,'Rig',Rig)
    def no_camera(*a,**kw):raise AssertionError('encoder-only must not open camera')
    monkeypatch.setattr(experiments,'CameraRecorder',no_camera)
    folder=tmp_path/'encoder-only'
    assert main(['collect','--suite','timing','--port','fixture','--execute','--encoder-only',
                 '--output',str(folder)])==0
    report=json.loads((folder/'report.json').read_text())
    assert report['sensor_mode']=='encoder_only'
    assert report['camera']['recorded'] is False
    assert report['independent_cart_motion_measured'] is False
    assert not (folder/'vision.ndjson').exists()
    assert not (folder/'vision-report.json').exists()
    review=c.review_campaign(folder,tmp_path/'review')
    assert review['integrity_ok'] and review['recording_complete']
    assert review['sensor_mode']=='encoder_only'
    assert not review['ready_for_fit'] and not review['hardware_accepted']
    assert any('independent camera' in b.lower() for b in review['blockers'])
    assert 'timing' in review


def test_encoder_only_manual_suites_are_rejected_before_resources(tmp_path):
    for suite in c.MANUAL:
        with pytest.raises(ValueError,match='manual'):
            c.collect_campaign(output=tmp_path/suite,port='fixture',suite=suite,
                               cart_restraint='held',encoder_only=True)
        assert not (tmp_path/suite).exists()


def test_second_trial_without_measurement_events_cannot_hide_behind_first(tmp_path):
    folder=tmp_path/'missing-second';c.rehearse(folder,suite='timing')
    (folder/'manifest.json').unlink()
    report=json.loads((folder/'report.json').read_text());report['synthetic']=False
    report['trials']=[dict(id='first',kind='timing',started_ns=1_000_000_000,finished_ns=1_500_000_000),
        dict(id='second',kind='timing',started_ns=1_500_000_001,finished_ns=2_000_000_000)]
    (folder/'report.json').write_text(json.dumps(report))
    with (folder/'rig.jsonl').open('a') as stream:
        for i in range(10,40):
            ns=1_000_000_000+i*10_000_000
            stream.write(json.dumps(dict(type='driven_reference',host_monotonic_ns=ns,host_policy_ns=ns,phase='feedback_cart_hold'))+'\n')
        for kind in ('action_request','policy_end','timing_transport_write_end','timing_policy_end','driven_start'):
            stream.write(json.dumps(dict(type=kind,host_monotonic_ns=1_450_000_000))+'\n')
    c.seal(folder)
    review=c.review_campaign(folder,tmp_path/'second-review')
    assert not review['analysis_usable']
    assert any('second' in b for b in review['blockers'])

@pytest.mark.parametrize('fail_at', [None, 1])
def test_collection_defers_cyclic_gc_until_serial_context_has_stopped(tmp_path, monkeypatch, fail_at):
    import gc
    Rig, Camera, instances, calls = fake_resources(tmp_path, monkeypatch, fail_at=fail_at)
    observed = []
    class CheckedRig(Rig):
        def __enter__(self):
            observed.append(('connect', gc.isenabled()))
            return super().__enter__()
        def __exit__(self, *args):
            observed.append(('disconnect', gc.isenabled()))
            return super().__exit__(*args)
    before = gc.isenabled()
    try:
        gc.enable()
        def collect():
            return c.collect_campaign(output=tmp_path/'gc-run', port='fixture', suite='timing',
                execute=True, repetitions=1, encoder_only=True, rig_factory=CheckedRig,
                camera_factory=Camera, emit=lambda _: None)
        if fail_at:
            with pytest.raises(RuntimeError, match='fault during trial'):
                collect()
        else:
            collect()
        assert observed == [('connect', False), ('disconnect', False)]
        assert gc.isenabled()
        assert calls[-1] == 'stop'
    finally:
        if not before:
            gc.disable()
