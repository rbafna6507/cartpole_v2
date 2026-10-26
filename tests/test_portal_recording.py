import io
import json
import zipfile
import pytest
from cartpole_sdk.portal.queue import Store, QueueError
from cartpole_sdk.portal.worker import run_once
from test_portal_worker import TrustedPipeFixture


def test_success_records_full_observations_actions_and_manifest(tmp_path):
    store=Store(tmp_path)
    job=store.submit('alice','one',b'x','x.py','simulation',.1)
    run_once(store,'w','sim',sandbox_factory=TrustedPipeFixture)
    with zipfile.ZipFile(io.BytesIO(store.recording(job['id'],'alice'))) as bundle:
        manifest=json.loads(bundle.read('manifest.json'))
        records=[json.loads(line) for line in bundle.read('telemetry.jsonl').splitlines()]
    assert manifest['outcome']['stopped'] is True
    assert manifest['job']['artifact']==job['artifact']
    assert manifest['coverage']['video']=='not_recorded'
    assert any(r['type']=='observation' and len(r['observation']['samples'])>=6 for r in records)
    assert any(r['type']=='action_request' for r in records)
    with pytest.raises(QueueError):store.recording(job['id'],'mallory')


def test_setup_failure_still_has_bundle(tmp_path):
    store=Store(tmp_path)
    job=store.submit('alice','one',b'x','x.py','simulation',.1)
    def broken():raise RuntimeError('failure')
    run_once(store,'w','sim',bridge_factory=broken)
    with zipfile.ZipFile(io.BytesIO(store.recording(job['id'],'alice'))) as bundle:
        manifest=json.loads(bundle.read('manifest.json'))
    assert manifest['outcome']['error']=='backend_failure'
    assert manifest['status']=='failed'


def test_recording_bound_reports_drops(tmp_path):
    from cartpole_sdk.portal.run_recording import RunRecorder
    recorder=RunRecorder(tmp_path,{'id':'test','artifact':'a'},max_bytes=100)
    for _ in range(10):recorder.emit('test',payload='x'*100)
    path=recorder.finalize('failed',{'error':'test'})
    with zipfile.ZipFile(path) as bundle:manifest=json.loads(bundle.read('manifest.json'))
    assert manifest['recording']['dropped_records']>0
    assert manifest['recording']['telemetry_bytes']<=100


def test_bundle_upload_bound_to_worker_and_immutable(tmp_path):
    from cartpole_sdk.portal.run_recording import RunRecorder
    store=Store(tmp_path/'store')
    job=store.submit('alice','one',b'x','x.py','simulation',.1)
    claimed=store.claim('w','sim')
    recorder=RunRecorder(tmp_path/'spool',claimed)
    bundle=recorder.finalize('failed',{'stopped':True}).read_bytes()
    with pytest.raises(QueueError):store.put_recording(job['id'],'evil',claimed['lease'],bundle)
    with pytest.raises(QueueError):store.put_recording(job['id'],'w','wrong',bundle)
    store.finish(job['id'],'w',claimed['lease'],'failed',{'stopped':True})
    store.put_recording(job['id'],'w',claimed['lease'],bundle)
    store.put_recording(job['id'],'w',claimed['lease'],bundle)
    recorder=RunRecorder(tmp_path/'spool',claimed)
    other=recorder.finalize('failed',{'stopped':False}).read_bytes()
    with pytest.raises(QueueError):store.put_recording(job['id'],'w',claimed['lease'],other)
    assert store.recording(job['id'],'alice')==bundle


def test_upload_failure_preserves_local_bundle(tmp_path):
    class Unavailable(Store):
        def put_recording(self,*args):raise OSError('offline')
    store=Unavailable(tmp_path)
    store.submit('alice','one',b'x','x.py','simulation',.1)
    result=run_once(store,'w','sim',sandbox_factory=TrustedPipeFixture)
    assert result['result']['stopped'] is True
    assert result['result']['recording']['status']=='local_pending_upload'
    assert len(list((tmp_path/'recording-spool').glob('*/run.zip')))==1


def test_recorder_setup_failure_prevents_backend_creation(tmp_path):
    store=Store(tmp_path/'store')
    store.submit('alice','one',b'x','x.py','simulation',.1)
    invalid=tmp_path/'file';invalid.write_text('not a directory')
    touched=[]
    def factory():touched.append(True)
    result=run_once(store,'w','sim',bridge_factory=factory,recording_root=invalid)
    assert not touched
    assert result['status']=='failed'
    assert result['result']['recording']['status']=='unavailable'


def test_sensing_runs_in_separate_process_and_merges_after_stop(tmp_path):
    import os
    import threading
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    from cartpole_sdk.portal.run_recording import RunRecorder
    original={'schema':'cartpole-developer-stream-v1','channels':{'vision.raw':{'samples':[{'t':123,'angle':.5,'large':'x'*817000}]}},'cursors':{}}
    payload=(json.dumps(original)+'\n').encode()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            self.send_response(200);self.end_headers()
            try:self.wfile.write(payload*6)
            except OSError:pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    recorder=RunRecorder(tmp_path,{'id':'test','artifact':'a'})
    try:
        recorder.start_sensing(f'http://127.0.0.1:{server.server_port}',3)
        assert recorder.sensing_process.pid!=os.getpid()
        assert not hasattr(recorder,'sensing_thread')
        recorder.sensing_process.join(timeout=5)
        assert not recorder.sensing_process.is_alive()
        assert recorder.sensing_bytes==0  # no parent sensing processing during run
        recorder.emit('action_request',acceleration_m_s2=.1)
        path=recorder.finalize('succeeded',{'stopped':True})
        with zipfile.ZipFile(path) as bundle:
            records=[json.loads(line) for line in bundle.read('telemetry.jsonl').splitlines()]
            manifest=json.loads(bundle.read('manifest.json'))
        sensing=[r for r in records if r['type']=='sensing_envelope']
        assert sensing and sensing[0]['envelope']==original
        assert manifest['recording']['sensing_enqueued_bytes']<=3*1024*1024
        assert manifest['coverage']['vision']['collector_pid']!=os.getpid()
        assert manifest['coverage']['vision']['status']=='byte_limit'
        assert any(record['type']=='action_request' for record in records)
    finally:server.shutdown();server.server_close();thread.join()


def test_recorder_initialization_failure_does_not_block_unused_rig(tmp_path):
    store=Store(tmp_path/'store')
    store.submit('alice','one',b'x','x.py','simulation',.1)
    invalid=tmp_path/'file';invalid.write_text('not a directory')
    run_once(store,'w','sim',recording_root=invalid)
    second=store.submit('alice','two',b'x','x.py','simulation',.1)
    assert store.claim('w','sim')['id']==second['id']

@pytest.mark.parametrize('mode,expected',[('standard',False),('detailed',True)])
def test_recording_mode_preserves_default_sensing_and_requests_details(tmp_path,monkeypatch,mode,expected):
    from cartpole_sdk.portal.run_recording import RunRecorder
    calls=[]
    monkeypatch.setattr(RunRecorder,'start_sensing',lambda self,url,duration,**kwargs:calls.append(kwargs.get('detailed',False)))
    store=Store(tmp_path/'store')
    job=store.submit('alice','one',b'x','x.py','simulation',.1,recording=mode)
    result=run_once(store,'w','sim',sandbox_factory=TrustedPipeFixture,sensing_url='http://127.0.0.1:1')
    assert result['status']=='succeeded'
    assert calls==[expected]
    assert store.recording(job['id'],'alice')


@pytest.mark.parametrize('snapshot_matches',[False,True])
def test_post_arm_observation_consumed_by_first_action_is_recorded(tmp_path,snapshot_matches):
    from dataclasses import replace
    from cartpole_sdk.portal.worker import HardwareBridge, SimulationBridge
    class ArmChangesObservation(HardwareBridge):
        def prepare(self,duration,identifier):
            self.sim=SimulationBridge();self.current=self.sim.prepare(duration,identifier)
            self.session=self.sim.session;self.done=False
            from types import SimpleNamespace
            self.rig=SimpleNamespace(state=self.sim.env.ground_truth)
            return self.current
        def arm(self,duration):self.current=replace(self.current,sequence=self.current.sequence+100000)
        def selected(self):return self.current
        def complete(self):return self.done
        def advance(self,value,sequence):
            from dataclasses import dataclass
            @dataclass(frozen=True)
            class CachedState:
                unwrapped_tick:int
                received_ns:int
                theta:float
            # Simulate the reader receiving a newer STATE between observation
            # selection and recorder sampling, without touching a serial device.
            self.rig.state=CachedState(self.current.sequence+(0 if snapshot_matches else 10),123456,.2)
            self.done=True
            return self.current
        def diagnostics(self):return {}
        def stop(self):return True
        def close(self):self.sim.close()
    store=Store(tmp_path/'store')
    job=store.submit('alice','one',b'x','x.py','magnetic-step',.1,recording='detailed')
    store.approve(job['id'],'operator',artifact=job['artifact'],sensor_source='magnetic-step',duration=.1)
    result=run_once(store,'w','synthetic',bridge_factory=ArmChangesObservation,sandbox_factory=TrustedPipeFixture,sensor_source='magnetic-step')
    assert result['status']=='succeeded'
    with zipfile.ZipFile(io.BytesIO(store.recording(job['id'],'alice'))) as bundle:
        records=[json.loads(line) for line in bundle.read('telemetry.jsonl').splitlines()]
    first_call=next(i for i,r in enumerate(records) if r['type']=='policy_call')
    consumed=records[first_call]['observation_sequence']
    assert consumed>=100000
    assert any(r['type']=='observation' and r['observation']['sequence']==consumed for r in records[:first_call])

    board=next(r for r in records if r['type']=='board_state')
    assert 'observation_sequence' not in board
    assert board['nearest_observation_sequence']==consumed
    assert board['snapshot_matches_observation'] is snapshot_matches
    assert board['state']['received_ns']==123456
    assert board['state']['unwrapped_tick']==consumed+(0 if snapshot_matches else 10)


def test_detailed_collector_requests_bounded_history_and_reports_limits(tmp_path):
    import threading
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    from urllib.parse import urlsplit,parse_qs
    from cartpole_sdk.portal.run_recording import RunRecorder
    requests=[]
    envelope={'schema':'cartpole-developer-stream-v1','channels':{},'cursors':{},'gaps':['retained-source-gap']}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            requests.append(parse_qs(urlsplit(self.path).query))
            self.send_response(200);self.end_headers();self.wfile.write((json.dumps(envelope)+'\n').encode())
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    recorder=RunRecorder(tmp_path,{'id':'test','artifact':'a','recording':'detailed'})
    try:
        recorder.start_sensing(f'http://127.0.0.1:{server.server_port}',1,detailed=True)
        recorder.sensing_process.join(timeout=5)
        path=recorder.finalize('succeeded',{})
        with zipfile.ZipFile(path) as bundle:
            manifest=json.loads(bundle.read('manifest.json'))
            records=[json.loads(line) for line in bundle.read('telemetry.jsonl').splitlines()]
        assert requests[0]['limit']==['128'] and requests[0]['max_hz']==['30']
        assert manifest['recording']['max_sensing_bytes']==8*1024*1024
        assert manifest['coverage']['vision']['sample_limit']==128
        assert records[0]['envelope']['gaps']==['retained-source-gap']
    finally:server.shutdown();server.server_close();thread.join()
