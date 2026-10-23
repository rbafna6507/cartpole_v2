import pytest
from cartpole_sdk.portal import worker
from cartpole_sdk.portal.queue import Store, QueueError

def test_remote_claim_failure_is_distinct_from_active_run_failure(monkeypatch):
    queue=worker.RemoteQueue('http://127.0.0.1:8765','test-token')
    def fail(*args,**kwargs):raise worker.WorkerError('transport unavailable')
    monkeypatch.setattr(queue,'_request',fail)
    with pytest.raises(worker.ClaimUnavailable):queue.claim('w','rig')
    with pytest.raises(worker.WorkerError) as failure:queue.heartbeat('a'*32,'w','lease')
    assert not isinstance(failure.value,worker.ClaimUnavailable)

def test_main_retries_only_idle_claim_with_bounded_backoff(tmp_path,monkeypatch):
    token=tmp_path/'token';token.write_text('test-token')
    sleeps=[];calls=[]
    def run(*args,**kwargs):
        calls.append(1)
        if len(calls)<=5:raise worker.ClaimUnavailable('unavailable')
        raise KeyboardInterrupt()
    monkeypatch.setattr(worker,'run_once',run)
    monkeypatch.setattr(worker.time,'sleep',sleeps.append)
    status=worker.main(['--portal','http://127.0.0.1:8765','--token-file',str(token),'--rig-id','rig','--backend','hardware','--port','/dev/not-opened'])
    assert status==130 and sleeps==[1.,2.,4.,5.,5.]

def test_lost_unarmed_claim_response_retains_lease_until_queue_expiry(tmp_path,monkeypatch):
    store=Store(tmp_path);store.submit('alice','one',b'x','policy.py','simulation',.1)
    remote=worker.RemoteQueue('http://127.0.0.1:8765','test-token')
    def lost(*args,**kwargs):
        store.claim('w','rig',now=100)
        raise worker.WorkerError('response lost')
    monkeypatch.setattr(remote,'_request',lost)
    with pytest.raises(worker.ClaimUnavailable):remote.claim('w','rig')
    assert store.claim('w','rig',now=101) is None
    assert store.list()[0]['status']=='claimed'
    assert store.claim('w','rig',now=110) is None
    assert store.list()[0]['status']=='failed'
    assert store.list()[0]['result']['stopped'] is True

def test_claim_retry_cannot_clear_an_expired_running_lease(tmp_path,monkeypatch):
    store=Store(tmp_path);store.submit('alice','one',b'x','policy.py','simulation',1)
    job=store.claim('w','rig',now=100)
    store.start(job['id'],'w',job['lease'],now=101)
    remote=worker.RemoteQueue('http://127.0.0.1:8765','test-token')
    def unavailable(*args,**kwargs):raise worker.WorkerError('portal unavailable')
    monkeypatch.setattr(remote,'_request',unavailable)
    with pytest.raises(worker.ClaimUnavailable):remote.claim('w','rig')
    store.recover(now=110)
    for _ in range(2):
        with pytest.raises(QueueError,match='blocked'):store.claim('w','rig',now=110)
    assert store.list()[0]['result']['stopped'] is False
