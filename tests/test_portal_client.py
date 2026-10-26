import hashlib
import threading
import time
import pytest
from cartpole_sdk.portal.queue import Store, QueueError
from cartpole_sdk.portal.server import make_server

@pytest.fixture
def portal(tmp_path):
    store = Store(tmp_path/'store', reservations_enabled=True)
    server = make_server(store, {'alice-secret-long': ('alice','submit'), 'bob-secret-long': ('bob','submit')}, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    from cartpole_sdk.portal.client import PortalClient
    client = PortalClient(f'http://127.0.0.1:{server.server_port}', 'alice-secret-long')
    try: yield store, client
    finally: server.shutdown(); server.server_close(); thread.join()

def test_explicit_recording_is_immutable(tmp_path):
    store=Store(tmp_path)
    job=store.submit('alice','same',b'x','x.py','simulation',.1,recording='detailed')
    assert job['recording']=='detailed'
    assert store.submit('alice','same',b'x','x.py','simulation',.1,recording='detailed')['id']==job['id']
    with pytest.raises(QueueError,match='idempotency'): store.submit('alice','same',b'x','x.py','simulation',.1)
    with pytest.raises(QueueError,match='recording'): store.submit('alice','bad',b'x','x.py','simulation',.1,recording='disabled')

def test_client_authenticated_submission_reservation_and_cancel(portal,tmp_path):
    store,client=portal
    source=tmp_path/'policy.py'; source.write_text('x=1')
    assert client.me()['principal']=='alice'
    booking=client.reserve('cartpole',time.time()+60,duration_minutes=2)
    assert client.reservations()['reservations'][0]['id']==booking['id']
    job=client.submit(source,sensor_source='magnetic-step',duration=.1,idempotency_key='one',reservation_id=booking['id'],recording='detailed')
    assert job['status']=='awaiting_approval' and job['recording']=='detailed'
    assert client.get(job['id'])['artifact']==hashlib.sha256(source.read_bytes()).hexdigest()
    assert client.cancel(job['id'])['status']=='cancelled'
    assert client.wait(job['id'],timeout=1)['status']=='cancelled'
    assert client.cancel_reservation(booking['id'])['status']=='cancelled'

def test_client_does_not_wait_forever_for_unexecuted_job(portal,tmp_path):
    _,client=portal
    source=tmp_path/'p.py';source.write_text('x=1')
    job=client.submit(source,sensor_source='simulation',duration=.1,idempotency_key='wait')
    with pytest.raises(TimeoutError):client.wait(job['id'],timeout=.05,poll_interval=.01)
    from cartpole_sdk.portal.client import PortalClient, PortalClientError
    other=PortalClient(client.origin,'bob-secret-long')
    with pytest.raises(PortalClientError):other.get(job['id'])

def finish_recording_job(store,tmp_path):
    from cartpole_sdk.portal.run_recording import RunRecorder
    submitted=store.submit('alice','recorded',b'x','x.py','simulation',.1,recording='detailed')
    claimed=store.claim('test-worker','test-sim',sensor_source='simulation')
    store.start(claimed['id'],'test-worker',claimed['lease'])
    store.finish(claimed['id'],'test-worker',claimed['lease'],'succeeded',{'stopped':True,'recording':{'status':'local_pending_upload'}})
    recorder=RunRecorder(tmp_path/'spool',claimed)
    recorder.emit('test_trace',sequence=1)
    bundle=recorder.finalize('succeeded',{'stopped':True})
    return claimed,bundle.read_bytes()

def test_collect_waits_for_upload_after_terminal_state(portal,tmp_path):
    store,client=portal
    job,bundle=finish_recording_job(store,tmp_path)
    def upload_later():
        time.sleep(.08)
        store.put_recording(job['id'],'test-worker',job['lease'],bundle)
    thread=threading.Thread(target=upload_later);thread.start()
    try:
        path=tmp_path/'result.zip'
        manifest=client.collect(job['id'],path,timeout=2,poll_interval=.01)
        assert path.read_bytes()==bundle
        assert manifest['coverage']['vision']=='requested but no sensing source configured'
        assert manifest['job']['recording']=='detailed'
        with pytest.raises(FileExistsError):client.download(job['id'],path)
    finally:thread.join()

def test_download_rejects_tampered_metadata_without_writing(portal,tmp_path):
    store,client=portal
    job,bundle=finish_recording_job(store,tmp_path)
    store.put_recording(job['id'],'test-worker',job['lease'],bundle)
    details=client.get(job['id']);details['result']['recording']['sha256']='0'*64
    from cartpole_sdk.portal.client import PortalClientError
    path=tmp_path/'result.zip'
    with pytest.raises(PortalClientError,match='integrity'):client.download(job['id'],path,job=details)
    assert not path.exists()

def test_collect_cancelled_before_claim_has_no_recording(portal,tmp_path):
    _,client=portal
    source=tmp_path/'p.py';source.write_text('x=1')
    job=client.submit(source,sensor_source='simulation',duration=.1,idempotency_key='cancel')
    client.cancel(job['id'])
    from cartpole_sdk.portal.client import PortalClientError
    with pytest.raises(PortalClientError,match='no downloadable'):client.collect(job['id'],tmp_path/'none.zip',timeout=.2)

@pytest.mark.parametrize('origin',['http://example.com','https://example.com/other','https://user:pass@example.com','https://example.com?token=x'])
def test_client_rejects_unsafe_origins(origin):
    from cartpole_sdk.portal.client import PortalClient
    with pytest.raises(ValueError):PortalClient(origin,'secret')


def test_client_negotiates_legacy_recording_mode(portal,tmp_path,monkeypatch):
    store,client=portal
    monkeypatch.setattr(client,'config',lambda:{})
    path=tmp_path/'p.py';path.write_text('x=1')
    from cartpole_sdk.portal.client import PortalClientError
    with pytest.raises(PortalClientError,match='recording mode'):client.submit(path,sensor_source='simulation',duration=.1,idempotency_key='legacy',recording='detailed')
    assert store.list('alice')==[]
    job=client.submit(path,sensor_source='simulation',duration=.1,idempotency_key='legacy')
    assert job['recording']=='standard'
