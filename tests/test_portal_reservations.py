import pytest
from cartpole_sdk.portal.queue import Store, QueueError


def physical(store, owner='alice', key='one', reservation_id=None):
    job=store.submit(owner,key,b'# policy','test.py','magnetic-step',1,now=100,reservation_id=reservation_id)
    store.approve(job['id'],'operator',artifact=job['artifact'],sensor_source=job['source'],duration=job['duration'])
    return job


def test_disabled_and_conflicts(tmp_path):
    store=Store(tmp_path)
    with pytest.raises(QueueError,match='disabled'):store.reserve('alice','cartpole',100,30,now=100)
    store=Store(tmp_path,reservations_enabled=True)
    r=store.reserve('alice','cartpole',100,30,now=100)
    with pytest.raises(QueueError,match='overlap'):store.reserve('bob','cartpole',200,30,now=100)
    assert store.reserve('bob','cartpole',1900,30,now=100)['starts_at']==1900
    assert len(store.reservations('alice',now=101))==1
    with pytest.raises(QueueError):store.cancel_reservation(r['id'],'bob')


def test_claim_exclusivity_window_and_binding(tmp_path):
    s=Store(tmp_path,reservations_enabled=True)
    r=s.reserve('alice','cartpole',110,1,now=100)
    bob=physical(s,'bob','bob')
    alice=physical(s,reservation_id=r['id'])
    assert s.claim('worker','cartpole',now=109,sensor_source='magnetic-step') is None
    assert s.claim('worker','other',now=111,sensor_source='magnetic-step')['id']==bob['id']
    claim=s.claim('worker','cartpole',now=111,sensor_source='magnetic-step')
    assert claim['id']==alice['id']
    with pytest.raises(QueueError):s.cancel_reservation(r['id'],'alice')


def test_reserved_cannot_start_outside_window_or_without_approval(tmp_path):
    s=Store(tmp_path,reservations_enabled=True)
    r=s.reserve('alice','cartpole',100,1,now=100)
    j=s.submit('alice','one',b'x','x.py','magnetic-step',1,reservation_id=r['id'],now=100)
    assert s.claim('w','cartpole',now=101) is None
    with pytest.raises(QueueError):s.submit('bob','bad',b'x','x.py','magnetic-step',1,reservation_id=r['id'],now=100)
    with pytest.raises(QueueError):s.submit('alice','sim',b'x','x.py','simulation',1,reservation_id=r['id'],now=100)
    s.approve(j['id'],'op',artifact=j['artifact'],sensor_source=j['source'],duration=1)
    assert s.claim('w','cartpole',now=159) is None
    s.cancel_reservation(r['id'],'alice')
    assert s.claim('w','cartpole',now=102) is None


def test_future_reservation_does_not_block_simulation(tmp_path):
    s=Store(tmp_path,reservations_enabled=True)
    s.reserve('alice','cartpole',110,1,now=100)
    j=s.submit('bob','sim',b'x','x.py','simulation',1,now=100)
    assert s.claim('w','sim',now=110,sensor_source='simulation')['id']==j['id']


def test_reservation_validation(tmp_path):
    s=Store(tmp_path,reservations_enabled=True)
    for start,duration in [(float('nan'),30),(100,31),(100,True),(90,30),(100,float('inf'))]:
        with pytest.raises(QueueError):s.reserve('alice','cartpole',start,duration,now=100)


def test_start_rechecks_reserved_time_after_claim(tmp_path):
    s=Store(tmp_path,reservations_enabled=True)
    r=s.reserve('alice','cartpole',100,1,now=100)
    j=physical(s,reservation_id=r['id'])
    claim=s.claim('w','cartpole',now=152)
    # A cancelled window cannot be bypassed by an already-issued lease.
    with s._tx() as db:db.execute('UPDATE reservations SET cancelled=1 WHERE id=?',(r['id'],))
    with pytest.raises(QueueError,match='reservation'):s.start(j['id'],'w',claim['lease'],now=153)


def test_disabled_restart_does_not_discard_existing_reservation(tmp_path):
    s=Store(tmp_path,reservations_enabled=True)
    r=s.reserve('alice','cartpole',100,1,now=100)
    physical(s,reservation_id=r['id'])
    physical(s,'bob','bob')
    restarted=Store(tmp_path)
    assert restarted.claim('w','cartpole',now=102) is None
    assert restarted.claim('w','cartpole',now=161)['owner']=='bob'


def test_active_job_prevents_new_conflicting_reservation(tmp_path):
    s=Store(tmp_path,reservations_enabled=True)
    physical(s)
    claim=s.claim('w','cartpole',now=100)
    assert claim
    with pytest.raises(QueueError,match='active experiment'):s.reserve('bob','cartpole',101,30,now=100)


def test_racing_reservations_only_one_succeeds(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    s=Store(tmp_path,reservations_enabled=True)
    def reserve(owner):
        try:return s.reserve(owner,'cartpole',100,30,now=100)
        except QueueError:return None
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(reserve,['alice','bob']))
    assert sum(r is not None for r in results)==1
