import time
import pytest
from cartpole_sdk.portal.runtime_store import RuntimeStore
from cartpole_sdk.portal.queue import QueueError

def running(tmp_path):
 s=RuntimeStore(tmp_path)
 j=s.submit('owner','one',b'def create_policy(): return None\n','test.py','simulation',55)
 c=s.claim('worker','rig');s.start(j['id'],'worker',c['lease'])
 return s,j['id'],c['lease']

def test_heartbeat_never_connects_to_database(tmp_path,monkeypatch):
 s,i,k=running(tmp_path)
 monkeypatch.setattr(s,'_connect',lambda:pytest.fail('heartbeat touched disk'))
 assert s.heartbeat(i,'worker',k)['status']=='running'

def test_wrong_identity_rejected(tmp_path):
 s,i,k=running(tmp_path)
 with pytest.raises(QueueError):s.heartbeat(i,'other',k)
 with pytest.raises(QueueError):s.heartbeat(i,'worker','wrong')

def test_monotonic_expiry_cannot_be_renewed(tmp_path,monkeypatch):
 s,i,k=running(tmp_path)
 monkeypatch.setattr('cartpole_sdk.portal.runtime_store.time.monotonic',lambda:10**20)
 with pytest.raises(QueueError):s.heartbeat(i,'worker',k)
 assert s.recover()==1

def test_live_runtime_survives_expired_persistent_lease(tmp_path):
 s,i,k=running(tmp_path)
 with s._tx() as db:db.execute('UPDATE jobs SET lease_until=0 WHERE id=?',(i,))
 assert s.recover()==0
 assert s.heartbeat(i,'worker',k)['status']=='running'
 assert s.finish(i,'worker',k,'succeeded',{'stopped':True})['status']=='succeeded'
 with pytest.raises(QueueError):s.heartbeat(i,'worker',k)

def test_restart_cannot_renew_previous_runtime(tmp_path):
 s,i,k=running(tmp_path)
 s.close()
 fresh=RuntimeStore(tmp_path)
 with pytest.raises(QueueError):fresh.heartbeat(i,'worker',k)

def test_cancel_visible_before_storage_write(tmp_path,monkeypatch):
 s,i,k=running(tmp_path)
 def unavailable():raise OSError('storage unavailable')
 monkeypatch.setattr(s,'_connect',unavailable)
 with pytest.raises(QueueError):s.cancel(i,'intruder')
 assert not s.heartbeat(i,'worker',k)['cancel_requested']
 with pytest.raises(OSError):s.cancel(i,'owner')
 assert s.heartbeat(i,'worker',k)['cancel_requested']

def test_sqlite_writer_lock_does_not_delay_heartbeat(tmp_path):
 s,i,k=running(tmp_path)
 db=s._connect()
 try:
  db.execute('BEGIN IMMEDIATE')
  began=time.monotonic()
  for _ in range(100):assert s.heartbeat(i,'worker',k)['status']=='running'
  assert time.monotonic()-began<.2
 finally:db.rollback();db.close()

def test_restart_marks_running_rig_blocked(tmp_path):
 s,i,k=running(tmp_path)
 s.close()
 fresh=RuntimeStore(tmp_path)
 assert fresh.recover()==1
 assert fresh.get(i)['result']['stopped'] is False
 with pytest.raises(QueueError):fresh.claim('worker','rig')

def test_failed_start_commit_does_not_publish_authority(tmp_path,monkeypatch):
 from contextlib import contextmanager
 s=RuntimeStore(tmp_path)
 j=s.submit('owner','one',b'def create_policy(): return None\n','test.py','simulation',55)
 c=s.claim('worker','rig');original=s._tx
 @contextmanager
 def fail_commit(**kwargs):
  with original(**kwargs) as db:
   yield db
   raise OSError('simulated commit failure')
 monkeypatch.setattr(s,'_tx',fail_commit)
 with pytest.raises(OSError):s.start(j['id'],'worker',c['lease'])
 with pytest.raises(QueueError):s.heartbeat(j['id'],'worker',c['lease'])

def test_fixed_monotonic_deadline_not_extended_by_renewal(tmp_path,monkeypatch):
 s,i,k=running(tmp_path)
 start=time.monotonic()
 for elapsed in range(1,56):
  monkeypatch.setattr('cartpole_sdk.portal.runtime_store.time.monotonic',lambda: start+elapsed)
  s.heartbeat(i,'worker',k)
 monkeypatch.setattr('cartpole_sdk.portal.runtime_store.time.monotonic',lambda:start+57)
 with pytest.raises(QueueError):s.heartbeat(i,'worker',k)

def test_cancel_racing_start_reaches_runtime(tmp_path,monkeypatch):
 from cartpole_sdk.portal.queue import Store
 s=RuntimeStore(tmp_path)
 j=s.submit('owner','one',b'def create_policy(): return None\n','test.py','simulation',55)
 c=s.claim('worker','rig');original=Store.cancel
 def interleaved_cancel(self,identifier,owner):
  # cancel's first memory lookup happened before start published its entry.
  self.start(identifier,'worker',c['lease'])
  return original(self,identifier,owner)
 monkeypatch.setattr(Store,'cancel',interleaved_cancel)
 s.cancel(j['id'],'owner')
 assert s.heartbeat(j['id'],'worker',c['lease'])['cancel_requested']

def test_wall_clock_jump_cannot_recover_live_monotonic_authority(tmp_path,monkeypatch):
 s,i,k=running(tmp_path);wall=time.time()
 monkeypatch.setattr('cartpole_sdk.portal.runtime_store.time.time',lambda:wall+3600)
 assert s.recover()==0
 assert s.heartbeat(i,'worker',k)['status']=='running'

def test_one_runtime_owner_per_directory(tmp_path):
 s,i,k=running(tmp_path)
 with pytest.raises(QueueError):RuntimeStore(tmp_path)
 s.close()
 fresh=RuntimeStore(tmp_path)
 with pytest.raises(QueueError):s.heartbeat(i,'worker',k)
 assert fresh.recover()==1

def test_preparation_has_fixed_budget_without_runtime_heartbeats(tmp_path):
 s=RuntimeStore(tmp_path)
 s.submit('owner','one',b'x','test.py','simulation',.1)
 j=s.claim('worker','rig')
 assert j['setup_heartbeat_required'] is False
 assert j['lease_until']==j['deadline']
 assert 34<j['deadline']-time.time()<=35

def test_slow_ready_transition_does_not_shorten_motion_duration(tmp_path):
 from cartpole_sdk.portal.worker import run_once,SimulationBridge
 from test_portal_worker import TrustedPipeFixture
 class Slow(RuntimeStore):
  def start(self,*args,**kwargs):
   time.sleep(.35)
   return super().start(*args,**kwargs)
 s=Slow(tmp_path);s.submit('owner','one',b'x','test.py','simulation',.1)
 armed=[]
 class Bridge(SimulationBridge):
  def arm(self,duration):armed.append(duration)
 result=run_once(s,'worker','rig',bridge_factory=Bridge,sandbox_factory=TrustedPipeFixture)
 assert result['status']=='succeeded'
 assert armed==[.1]

def test_cancel_during_start_visible_before_cancel_persistence(tmp_path,monkeypatch):
 from cartpole_sdk.portal.queue import Store
 s=RuntimeStore(tmp_path)
 j=s.submit('owner','one',b'x','test.py','simulation',55);c=s.claim('worker','rig')
 original=Store.cancel
 def before_persistence(self,identifier,owner):
  self.start(identifier,'worker',c['lease'])
  assert self.heartbeat(identifier,'worker',c['lease'])['cancel_requested']
  return original(self,identifier,owner)
 monkeypatch.setattr(Store,'cancel',before_persistence)
 s.cancel(j['id'],'owner')

def test_close_keeps_owner_lock_until_old_connections_drain(tmp_path):
 import threading
 s,i,k=running(tmp_path);db=s._connect();db.execute('BEGIN IMMEDIATE')
 done=threading.Event()
 closer=threading.Thread(target=lambda:(s.close(),done.set()));closer.start()
 try:
  time.sleep(.03)
  assert not done.is_set()
  with pytest.raises(QueueError):RuntimeStore(tmp_path)
 finally:db.rollback();db.close();closer.join(1)
 assert done.is_set()
 fresh=RuntimeStore(tmp_path);fresh.close()

def test_runtime_store_remote_worker_end_to_end(tmp_path):
 import threading
 from cartpole_sdk.portal.server import make_server
 from cartpole_sdk.portal.worker import RemoteQueue,run_once
 from test_portal_worker import TrustedPipeFixture
 s=RuntimeStore(tmp_path/'store');s.submit('owner','one',b'x','test.py','simulation',.1)
 server=make_server(s,{'test-worker-secret':('worker','worker')},port=0)
 thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 try:
  q=RemoteQueue(f'http://127.0.0.1:{server.server_port}','test-worker-secret')
  result=run_once(q,'worker','sim',sandbox_factory=TrustedPipeFixture,recording_root=tmp_path/'spool')
  assert result['status']=='succeeded' and result['result']['stopped']
  assert result['result']['recording']['status']=='available'
 finally:server.shutdown();server.server_close();thread.join();s.close()

def test_slow_commit_cannot_cross_next_reservation(tmp_path,monkeypatch):
 from contextlib import contextmanager
 s=RuntimeStore(tmp_path,reservations_enabled=True)
 wall=time.time();mono=time.monotonic();clock=[0.]
 s.reserve('other','rig',wall+7,30)
 j=s.submit('owner','one',b'x','test.py','magnetic-step',.5)
 s.approve(j['id'],'operator',artifact=j['artifact'],sensor_source=j['source'],duration=j['duration'])
 c=s.claim('worker','rig');assert c is not None
 original=s._tx
 @contextmanager
 def slow_commit(**kwargs):
  with original(**kwargs) as db:
   yield db
   clock[0]=7.5
 monkeypatch.setattr(s,'_tx',slow_commit)
 monkeypatch.setattr('cartpole_sdk.portal.runtime_store.time.time',lambda:wall+clock[0])
 monkeypatch.setattr('cartpole_sdk.portal.runtime_store.time.monotonic',lambda:mono+clock[0])
 with pytest.raises(QueueError,match='reservation elapsed'):s.start(j['id'],'worker',c['lease'])
 with pytest.raises(QueueError):s.heartbeat(j['id'],'worker',c['lease'])
